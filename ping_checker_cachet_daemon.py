import time
import sys
import json
import os
import requests
import threading
import functools
from requests.exceptions import ConnectionError, ReadTimeout, ConnectTimeout
from statistics import stdev
from dotenv import load_dotenv
from terminaltables import AsciiTable

print('Loading env file...')
load_dotenv()

# DotEnv caching
servers_path = os.getenv('SERVERS_FILE')
ping_history = int(os.getenv('PING_HISTORY'))
ip = os.getenv('IP')
interval = int(os.getenv('INTERVAL'))
alpha = float(os.getenv('ALPHA'))
margin = float(os.getenv('MARGIN'))
time_to_refresh = int(os.getenv('TIME_TO_REFRESH'))
api_key = os.getenv('API_KEY')
url = os.getenv('URL')
metric_id = int(os.getenv('METRIC_ID'))
acceptable_loss = float(os.getenv('ACCEPTABLE_LOSS'))
pinging_timeout = float(os.getenv('PINGING_TIMEOUT'))

# Static declaration
pop_time = time_to_refresh / ping_history
api_url = 'http://{0}/PING/{1}'
servers = []
headers = {
    'X-Cachet-Token': api_key
}


def eprint(*args, **kwargs):
    sys.stdout.flush()
    print(*args, file=sys.stderr, **kwargs)
    sys.stderr.flush()


def cache_dotenv():
    print('Loading env file... {0}'.format(load_dotenv(verbose=True, override=True)))

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
        headers

    # DotEnv caching
    servers_path = os.getenv('SERVERS_FILE')
    ping_history = int(os.getenv('PING_HISTORY'))
    ip = os.getenv('IP')
    interval = int(os.getenv('INTERVAL'))
    alpha = float(os.getenv('ALPHA'))
    margin = float(os.getenv('MARGIN'))
    time_to_refresh = int(os.getenv('TIME_TO_REFRESH'))
    api_key = os.getenv('API_KEY')
    url = os.getenv('URL')
    metric_id = int(os.getenv('METRIC_ID'))
    acceptable_loss = float(os.getenv('ACCEPTABLE_LOSS'))
    pinging_timeout = float(os.getenv('PINGING_TIMEOUT'))

    # Static declaration
    pop_time = time_to_refresh / ping_history
    api_url = 'http://{0}/PING/{1}'
    headers = {
        'X-Cachet-Token': api_key
    }

    print('DotEnv: {0}'.format(float(os.getenv('ALPHA'))))


class Server:

    def __init__(self, data):
        self.id = data[0]
        self.name = data[1]
        self.url = data[2]

        self.status = False
        self.last_check = 0
        self.lowest = []
        self.history = []
        self.received = []
        self.pings = 0
        self.avg = -1
        self.jitter = 0
        self.last_pop = 0

    def receive_ping(self, ms: int) -> object:
        self.pings += 1

        # Received history
        self.received.insert(0, ms is not False)

        if len(self.received) > ping_history:
            self.received.pop()

        # Avoid logic when negative
        if not ms or ms < 0:
            return

        # Compute max
        if len(self.lowest) > 0:
            m = max(self.lowest)
        else:
            m = 0

        # Compute average
        if self.avg == -1:
            self.avg = ms
        else:
            self.avg = self.avg * (1 - alpha) + ms * alpha

        # Populate ping history
        if m > ms or len(self.lowest) < ping_history:
            self.lowest.append(ms)

            # Remove if full
            while len(self.lowest) > ping_history:
                self.lowest.remove(m)

        # Populate history
        self.history.insert(0, ms)
        while len(self.history) > ping_history:
            self.history.pop()

        # Check for pop
        if time.time() - self.last_pop > pop_time and len(self.lowest) > 0:
            self.lowest.remove(min(self.lowest))
            self.last_pop = time.time()

    def health_check(self):
        try:
            if time.time() - self.last_check > 30:
                self.last_check = time.time()
                res = requests.get('http://{0}/'.format(self.url), timeout=1)

                # Check for successful response
                if res.status_code != 200:
                    eprint('Health check raised error for status {0}'.format(res.status_code))
                    raise ConnectionError

                self.status = True
                print('Server {0} turned ON.'.format(self.url))
        except:
            print('Server {0} turned offline as it\'s not responding...'.format(self.url))
            self.status = False

    def send_ping(self):
        self.health_check()

        if self.status:
            ms = ping(sv.url, ip)

            self.receive_ping(ms)

    def abnormal(self):
        if not self.status:
            return False

        return (((self.avg > self.minimum() + max(self.stdev(), self.minimum() * margin) * 2)
                 or
                 (self.loss() > acceptable_loss))
                and
                len(self.history) > ping_history)

    def loss(self):
        if len(self.received) == 0:
            return 0

        return 1 - (sum(self.received) / len(self.received))

    def minimum(self):
        if len(self.lowest) == 0:
            return 0

        return sum(self.lowest) / len(self.lowest)

    def ping(self):
        self.ping_thread = threading.Thread(target=self.send_ping)

        self.ping_thread.start()

    def wait(self):
        self.ping_thread.join()

    def stdev(self):
        if len(self.history) > 1:
            return stdev(self.history)
        else:
            return 0


def ping(src, dst):
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

    return int(res['ms'])


def load_servers():
    file = open(servers_path, 'r')
    svs = json.load(file)

    print('Loaded {0} servers from file'.format(len(svs)))

    # Create object
    for data in svs:
        servers.append(Server(data))


load_servers()

while True:
    # Reload DotEnv
    cache_dotenv()

    # Dispatch threads
    for sv in servers:
        sv.ping()

    # Join them
    for sv in servers:
        sv.wait()

    abnormal = 0

    # Check for abnormal servers
    table_data = [['Server URL', 'Average', 'History', 'Loss', 'Abnormal']]
    for sv in servers:
        if sv.abnormal():
            abnormal += 1
        table_data.append([
            sv.url,
            '{0:.2f} +-{1:.2f}'.format(sv.avg, sv.stdev()),
            len(sv.history),
            '{0}'.format(sv.loss()),
            'YES' if sv.abnormal() else '---'
        ])

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
    sys.stdout.flush()
    time.sleep(interval)
