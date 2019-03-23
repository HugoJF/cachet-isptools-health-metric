for filename in ./dbs/*; do
    echo rendering $filename
    name=$(basename $filename)
    
    rrdtool graph graphs/"${name/.rrd/}_1d".png \
    --imgformat PNG \
    --title="Server latency history (last 24 hours)" \
    --vertical-label "Ping (ms)" \
    --end=n-1min \
    --start=n-1441min \
    --color=BACK#CCCCCC \
    --color=CANVAS#FEFEFE \
    --color=SHADEB#9999CC \
    --height=250 \
    --alt-autoscale \
    --watermark "Servidores de_nerdTV | Powered by ISPTools" \
    --slope-mode \
    DEF:pingg=dbs/$name:ping:AVERAGE \
    DEF:pingminn=dbs/$name:ping:MIN:step=500 \
    DEF:pingmaxx=dbs/$name:ping:MAX:step=500 \
    CDEF:ping=pingg,0,MAX,200,MIN \
    CDEF:pingmax=pingmaxx,200,MIN \
    CDEF:pingmin=pingminn,0,MAX \
    CDEF:err=pingmax,190,GT \
    CDEF:delta=pingmax,pingmin,- \
    VDEF:lastmin=pingmin,LAST \
    VDEF:lastmax=pingmax,LAST \
    VDEF:lastdelta=delta,AVERAGE \
    VDEF:last=ping,LAST \
    LINE:pingmin#00ff0099:"Last Minimum\:":STACK \
    GPRINT:lastmin:"   %03.2lf ms\l" \
    AREA:delta#66666688:"Last Delta\:    ":STACK \
    GPRINT:lastdelta:" %03.2lf ms\l" \
    LINE:pingmax#ff000099:"Last Maximum\:" \
    GPRINT:lastmin:"   %03.2lf ms\l" \
    LINE:ping#0000ff:"Last Ping\: " \
    GPRINT:last:"     %03.2lf ms\l" \
    TICK:err#ff0000:0.05:"  Overflow \l"
done
