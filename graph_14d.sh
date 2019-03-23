for filename in ./dbs/*; do
    echo rendering $filename
    name=$(basename $filename)
    
    rrdtool graph graphs/"${name/.rrd/}_14d".png \
    --imgformat PNG \
    --title="Server latency history (last 14 days)" \
    --vertical-label "Ping (ms)" \
    --end=n-1min \
    --start=n-20161min \
    --color=BACK#CCCCCC \
    --color=CANVAS#FEFEFE \
    --color=SHADEB#9999CC \
    --height=250 \
    --alt-autoscale \
    --watermark "Servidores de_nerdTV | Powered by ISPTools" \
    --slope-mode \
    DEF:pingg=dbs/$name:ping:AVERAGE \
    CDEF:ping=pingg,0,MAX,200,MIN \
    CDEF:err=ping,190,GT \
    VDEF:last=ping,LAST \
    LINE:ping#0000ff:"Last Ping\: " \
    GPRINT:last:"     %03.2lf ms\l" \
    TICK:err#ff0000:0.05:"  Overflow \l"
done
