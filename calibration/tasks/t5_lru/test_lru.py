import pytest
from lru import LRU
def test_basic():
    c=LRU(2); c.put("a",1); c.put("b",2); assert c.get("a")==1
    c.put("c",3); assert c.get("b") is None and c.get("c")==3 and c.get("a")==1
def test_update_moves_to_recent():
    c=LRU(2); c.put("a",1); c.put("b",2); c.put("a",9); c.put("c",3)
    assert c.get("b") is None and c.get("a")==9
def test_keys_order():
    c=LRU(3); c.put("a",1); c.put("b",2); c.put("c",3); c.get("a")
    assert c.keys()==["b","c","a"]
def test_capacity_error():
    with pytest.raises(ValueError): LRU(0)
def test_many():
    c=LRU(1000)
    for i in range(5000): c.put(i,i)
    assert c.get(0) is None and c.get(4999)==4999 and len(c.keys())==1000
