Cachet health metric using ISPTools API

Daemon written in Python 3 to display how many test points have abnormal behavior pinging a server

### DotEnv variables

`URL` - Cachet API URL

`METRIC_ID` - What Metric ID should be POSTed

`API_KEY` - Cachet API key

`INTERVAL` - Seconds to wait before requesting Ping information again

`SERVERS_FILE` - ISPTools servers file (JSON)

`PING_HISTORY` - How many pings will be using to compute standard deviation

`IP` - What IP should be tested

`ALPHA` - How fast the moving average should change

`MARGIN` - Maximum margin average can be above ideal average

`TIME_TO_REFRESH` - How long will it take to refresh the ideal average

`ACCEPTABLE_LOSS` - Maximum acceptable packet loss rate