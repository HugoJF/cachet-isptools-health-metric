for filename in ./dbs/*; do
    echo rendering $filename
    name=$(basename $filename)
    
    rrdtool graph graphs/"${name/.rrd/}".png \
    --imgformat PNG \
    --title="Server latency history (last hour)" \
    --vertical-label "Ping (ms)" \
    --start=n-62min \
    --end=n-2min \
    --color=BACK#CCCCCC \
    --color=CANVAS#FEFEFE \
    --color=SHADEB#9999CC \
    --height=250 \
    --watermark "Servidores de_nerdTV | Powered by ISPTools" \
    --slope-mode \
    DEF:pingmin=dbs/$name:ping:MIN:step=120 \
    DEF:ping=dbs/$name:ping:AVERAGE \
    DEF:pingmax=dbs/$name:ping:MAX:step=120 \
    CDEF:delta=pingmax,pingmin,- \
    VDEF:lastmin=pingmin,LAST \
    VDEF:lastmax=pingmax,LAST \
    VDEF:lastdelta=delta,LAST \
    VDEF:last=ping,LAST \
    LINE:pingmin#00ff00aa:"Minimum\:":STACK \
    GPRINT:lastmin:"   %03.2lf ms\l" \
    AREA:delta#66666688:"Variation\:":STACK \
    GPRINT:lastdelta:" %03.2lf ms\l" \
    LINE:pingmax#ff0000aa:"Maximum\:" \
    GPRINT:lastmin:"   %03.2lf ms\l" \
    LINE:ping#0000ff:"Ping\: " \
    GPRINT:last:"     %03.2lf ms\l"
done