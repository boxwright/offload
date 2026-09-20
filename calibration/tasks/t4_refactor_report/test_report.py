import report, inspect, re
ROWS=[("widget",2,3.5),("gadget",1,10.0)]
EXP="widget          2      3.50        7.00\ngadget          1     10.00       10.00\nTOTAL                             17.00"
def test_sales(): assert report.render_sales(ROWS)==EXP
def test_refunds(): assert report.render_refunds(ROWS)=="REFUNDS\n"+EXP
def test_inventory(): assert report.render_inventory(ROWS)=="INVENTORY\n"+EXP
def test_dedup():
    src=inspect.getsource(report)
    assert src.count("{total:>12.2f}")==1, "row formatting must exist once"
    assert src.count("TOTAL")==1, "TOTAL row must exist once"
