import re
import time
import sys
import json
import os
import requests
import threading
import subprocess
import git
import sentry_sdk
from requests.exceptions import ConnectionError, ReadTimeout, ConnectTimeout
from statistics import stdev
from dotenv import load_dotenv
from terminaltables import AsciiTable
from flask import Flask
from flask_restful import Api, Resource, reqparse
from flask_cors import CORS


######################
# Method definitions #
######################


def cache_dotenv():
    """
    Loads DotEnv file to variables
    """
    print('Loading DotEnv file: {0}'.format(load_dotenv(verbose=True, override=True)))

    global \
        servers_path, \
        ping_history, \
        ip, \
        interval, \
        alpha, \
        margin, \
        time_to_refresh, \
        api_key, \
        url, \
        metric_id, \
        acceptable_loss, \
        pop_time, \
        api_url, \
        headers, \
        pinging_timeout, \
        jitter_margin, \
        sentry_url, \
        host, \
        port, \
        health_test_ip, \
        ping_interval, \
        worker_count, \
        rrd_path

    # DotEnv caching

    # Path to servers.json file
    servers_path = os.getenv('SERVERS_FILE')

    # How many pings will be stored per server
    ping_history = int(os.getenv('PING_HISTORY'))

    # IP to bind backend
    ip = os.getenv('IP')

    # Refreshing interval between requests
    interval = int(os.getenv('INTERVAL'))

    # How fast the moving average for pings will change
    alpha = float(os.getenv('ALPHA'))

    # How high can the average ping go beyond the baseline
    margin = float(os.getenv('MARGIN'))

    # How many seconds to completely refresh baseline values
    time_to_refresh = int(os.getenv('TIME_TO_REFRESH'))

    # Cachet API key
    api_key = os.getenv('API_KEY')

    # Cachet URL
    url = os.getenv('URL')

    # What metric should be posted
    metric_id = int(os.getenv('METRIC_ID'))

    # Acceptable packet loss
    acceptable_loss = float(os.getenv('ACCEPTABLE_LOSS'))

    # Ping request timeout
    pinging_timeout = float(os.getenv('PINGING_TIMEOUT'))

    # Relation between baseline and maximum jitter
    jitter_margin = float(os.getenv('JITTER_MARGIN'))

    # Sentry URL
    sentry_url = os.getenv('SENTRY_URL')

    # Flask host bind
    host = os.getenv('HOST')

    # Flask port bind
    port = os.getenv('PORT')

    # Reliable IP to test if PING API is responding correctly
    health_test_ip = os.getenv('HEALTH_TEST_IP')

    # Worker refresh interval
    ping_interval = float(os.getenv('PING_INTERVAL'))

    # Worker count
    worker_count = int(os.getenv('WORKER_COUNT'))

    # RRD Path to store databases
    rrd_path = os.getenv('RRD_PATH', 'dbs/')

    # Static declaration
    pop_time = time_to_refresh / ping_history
    api_url = 'http://{0}/PING/{1}'
    headers = {
        'X-Cachet-Token': api_key
    }

    print('DotEnv: {0}'.format(float(os.getenv('ALPHA'))))


def eprint(*args, **kwargs) -> None:
    """
    Error printing
    """
    sys.stdout.flush()
    print(*args, file=sys.stderr, **kwargs)
    sys.stderr.flush()


def check_for_new_version() -> None:
    """
    Checks for new commit SHAs on current directory
    """
    global current_sha

    repo = git.Repo()
    sha = repo.head.object.hexsha

    if current_sha is None:
        print('Running on commit #{0}'.format(sha))
        current_sha = sha
    elif current_sha != sha:
        print('New version found, quitting...')
        quit(0)


def ping(src: str, dst: str) -> int or False:
    """
    Pinging function
    :param src: IP address
    :param dst: IP address
    :return: int: ping in milliseconds or False if ping failed
    """
    global pinging_timeout

    url = api_url.format(src, dst)

    # Send GET request
    try:
        res = requests.get(url, timeout=pinging_timeout)
    except:
        eprint('Exception while requesting pings')
        return False

    # Check for successful response
    if res.status_code != 200:
        raise ConnectionError

    # Parse response JSON
    res = json.loads(res.text)

    # Check if response is valid
    if res['err']:
        return False

    return int(res['ms']), int(res['ttl'])


def load_servers() -> None:
    file = open(servers_path, 'r')
    svs = json.load(file)

    print('Loaded {0} servers from file'.format(len(svs)))

    # Create object
    for data in svs:
        servers.append(Server(data))


def create_rrd(path) -> None:
    subprocess.call(
        'rrdtool create {0} '
        '--step 10 '
        'DS:ping:GAUGE:120:0:5000 ' 
        'RRA:AVERAGE:0.5:6:4320 '
        'RRA:MIN:0.5:6:4320 '
        'RRA:MAX:0.5:6:4320 '
        'RRA:AVERAGE:0.5:60:4320 '
        'RRA:MIN:0.5:60:4320 '
        'RRA:MAX:0.5:60:4320'.format(path),
        shell=True
    )


def update_rrd(path: str, ping: int, ttl: int, jitter: int):
    command = 'rrdtool update {0} N:{1}:{2}:{3}'.format(path, ping, ttl, jitter)

    print('exec: {0}'.format(command))

    subprocess.call(
        command,
        shell=True
    )


###########
# Classes #
###########


class Server:
    def __init__(self, data):
        self.id = data[0]
        self.name = data[1]
        self.url = data[2]

        self.online = False
        self.last_check = 0
        self.last_ping = None
        self.lowest = []
        self.history = []
        self.received = []
        self.pings = 0
        self.avg = -1
        self.jitter = 0
        self.last_pop = 0

        self.check_rrd()

    def toJSON(self) -> object:
        return {
            'id': self.id,
            'name': self.name,
            'url': self.url,
            'online': self.online,
            'last_check': self.last_check,
            'last_ping': self.last_ping,
            'abnormal': self.abnormal(),
            'abnormal_ping': self.abnormal_ping(),
            'abnormal_loss': self.abnormal_loss(),
            'abnormal_jitter': self.abnormal_jitter(),
            'ping': self.avg,
            'loss': self.loss(),
            'pings': self.pings,
            'ping_rate': self.compute_average_ping_rate(),
            'baseline': self.minimum(),
            'jitter': self.stdev(),
        }

    def touch(self) -> None:
        self.last_ping = time.time()

    def check_rrd(self) -> None:
        path = self.get_rrd_path()

        if not os.path.isfile(path):
            print('Database not found, creating it: {0}'.format(path))
            create_rrd(path)

    def get_rrd_path(self) -> str:
        name = re.sub(r"[^A-Za-z0-9]", "_", '{0}'.format(self.url))

        return '{0}{1}.rrd'.format(rrd_path, name)

    def receive_ping(self, ms: int, ttl: int) -> None:
        self.pings += 1
        self.touch()

        # Received history
        self.received.insert(0, ms is not False)

        update_rrd(self.get_rrd_path(), ms, ttl, self.jitter)

        # Avoid logic when negative
        if not ms or ms < 0:
            return

        self.compute_average(ms)
        self.populate_baseline(ms)
        self.add_ping(ms)
        self.pop_history()
        self.pop_baseline()

    def compute_average_ping_rate(self) -> float:
        return self.pings / (time.time() - start_time)

    def compute_average(self, ms) -> None:
        # Compute average
        if self.avg == -1:
            self.avg = ms
        else:
            self.avg = self.avg * (1 - alpha) + ms * alpha

    def baseline_max(self) -> int:
        # Compute max
        if len(self.lowest) > 0:
            return max(self.lowest)
        else:
            return 0

    def populate_baseline(self, ms) -> None:
        max = self.baseline_max()

        # Populate ping history
        if max > ms or len(self.lowest) < ping_history:
            self.lowest.append(ms)

            # Remove if full
            while len(self.lowest) > ping_history:
                self.lowest.remove(max)

    def add_ping(self, ms: int) -> None:
        # Populate history
        self.history.insert(0, ms)
        while len(self.history) > ping_history:
            self.history.pop()

    def pop_history(self) -> None:
        # Remove oldest ping if above limit
        if len(self.received) > ping_history:
            self.received.pop()

    def pop_baseline(self) -> None:
        # Check for pop
        if time.time() - self.last_pop > pop_time and len(self.lowest) > 0:
            self.lowest.remove(min(self.lowest))
            self.last_pop = time.time()

    def health_check(self) -> None:
        try:
            if time.time() - self.last_check > 30:
                # Update timer
                self.last_check = time.time()

                # Request information from server
                res = requests.get('http://{0}/'.format(self.url), timeout=1)

                # Check for successful response
                if res.status_code != 200:
                    eprint('Health check raised error for status {0}'.format(res.status_code))
                    raise ConnectionError

                # Attempts to ping reliable IP
                res = requests.get(api_url.format(self.url, health_test_ip))

                # Raise error for reliable IP
                if res.status_code != 200:
                    eprint('Health check raised error for status {0} on reliable IP: {1}'.format(res.status_code,
                                                                                                 health_test_ip))

                # If reached this point, node is healthy
                self.online = True
                print('Server {0} turned ON.'.format(self.url))
        except:
            print('Server {0} turned offline as it\'s not responding...'.format(self.url))
            self.online = False

    def send_ping(self):
        self.health_check()

        # Only ping if server is considered healthy
        if self.online:
            ms, ttl = ping(self.url, ip)

            self.receive_ping(ms, ttl)

    def abnormal_ping(self):
        return (
                (self.avg > self.minimum() + max(self.stdev(), self.minimum() * margin) * 2)
                and
                len(self.history) >= ping_history
        )

    def abnormal_loss(self):
        return (
                (self.loss() > acceptable_loss)
                and
                self.pings >= ping_history
        )

    def abnormal_jitter(self):
        return (
                self.stdev() > self.minimum() * jitter_margin
        )

    def abnormal(self):
        if not self.online:
            return False

        return self.abnormal_ping() or self.abnormal_loss() or self.abnormal_jitter()

    def loss(self):
        if len(self.received) == 0:
            return 0

        return 1 - (sum(self.received) / len(self.received))

    def minimum(self):
        if len(self.lowest) == 0:
            return 0

        return sum(self.lowest) / len(self.lowest)

    def ping(self):
        self.last_check = time.time()
        self.send_ping()

    def expired(self):
        return time.time() - self.last_check > 5

    def wait(self):
        self.ping_thread.join()

    def stdev(self):
        if len(self.history) > 1:
            return stdev(self.history)
        else:
            return 0


#################
# API Resources #
#################


class ServerApi(Resource):
    def get(self):
        svs = list(map(lambda x: x.toJSON(), servers))

        return svs


class PingsApi(Resource):
    def get(self, id):
        sv = list(filter(lambda x: int(x.id) == int(id), servers))

        if len(sv) == 0:
            return {
                'error': True
            }

        return {
            'error': False,
            'pings': sv[0].history,
        }


######################
# Main runner method #
######################

def worker():
    while True:
        oldest = None
        oldest_time = time.time()

        for sv in servers:  # type: Server
            if oldest is None or sv.last_ping is None or sv.last_ping < oldest_time:
                oldest = sv
                oldest_time = sv.last_ping

        if oldest.last_ping is None:
            expired = True
        else:
            expired = (time.time() - oldest.last_ping) > 1

        if oldest is not None and expired:
            oldest.touch()
            oldest.health_check()
            oldest.ping()

        time.sleep(ping_interval)


def runner():
    load_servers()

    for i in range(0, worker_count):
        t = threading.Thread(target=worker)
        t.start()

    while True:
        # Check if there is a new version
        check_for_new_version()

        # Reload DotEnv
        cache_dotenv()

        abnormal = 0

        # Check for abnormal servers
        table_data = [['Server URL', 'Average', 'History', 'Pings', 'Loss', 'Abnormal']]
        for sv in servers:
            if sv.abnormal():
                abnormal += 1

            table_data.append([
                sv.url,
                '{0:.2f} +-{1:.2f}'.format(sv.avg, sv.stdev()),
                len(sv.history),
                sv.pings,
                '{0}'.format(sv.loss()),
                'YES' if sv.abnormal() else '---'
            ])

        # Build and print table
        table = AsciiTable(table_data)

        print(table.table)

        # Debug
        print('Currently {0} abnormal servers.'.format(abnormal))

        # Build POST data
        data = {
            'value': abnormal,
            'timestamp': int(time.time()),
        }

        # Send POST
        try:
            res = requests.post(url + '/api/v1/metrics/{0}/points'.format(metric_id), data=data, headers=headers)
            print('Status code for POST: {0}'.format(res.status_code))
        except:
            print('Error posting data')

        # Flush and wait
        print('Sleeping {0} seconds with {1} threads alive'.format(interval, threading.active_count()))
        sys.stdout.flush()
        time.sleep(interval)


#############################
# DotEnv variable re-naming #
#############################


# Loads environment file first
print('Loading DotEnv file...')
load_dotenv()

# Save variables
cache_dotenv()

######################
# Static declaration #
######################

# Stores start time for statistics
start_time = time.time()

# SHA from current commit
current_sha = None

# How long to wait between baseline pops
pop_time = time_to_refresh / ping_history

# API URL pattern
api_url = 'http://{0}/PING/{1}'

# Server instances list
servers = []

# Header that is sent while POSTing to Cachet
headers = {
    'X-Cachet-Token': api_key
}

#########################
# Static initialization #
#########################

# Initialize sentry
sentry_sdk.init(sentry_url)

# Initialize Flask
app = Flask('PingChecker')
api = Api(app)

# Setup CORS
CORS(app)

# Prepare runner thread
runner_thread = threading.Thread(target=runner)
runner_thread.start()

# Prepare API resources
api.add_resource(ServerApi, '/servers/')
api.add_resource(PingsApi, '/pings/<int:id>')

# Run API
app.run(debug=True, host=host, port=port)
