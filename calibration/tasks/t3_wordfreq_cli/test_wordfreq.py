import subprocess, sys, os
from wordfreq import top_words
HERE=os.path.dirname(__file__)
def _w(name, text):
    p=os.path.join(HERE,name); open(p,"w").write(text); return p
def test_top_words():
    p=_w("a.txt","The cat and the dog. The DOG!")
    assert top_words([p],2)==[("the",3),("dog",2)]
def test_ties_alpha():
    p=_w("b.txt","b a c a b c")
    assert top_words([p],3)==[("a",2),("b",2),("c",2)]
def test_cli_output():
    p=_w("c.txt","x y y")
    r=subprocess.run([sys.executable,os.path.join(HERE,"wordfreq.py"),"-n","1",p],capture_output=True,text=True)
    assert r.returncode==0 and r.stdout.strip()=="y 2"
def test_missing_file():
    r=subprocess.run([sys.executable,os.path.join(HERE,"wordfreq.py"),os.path.join(HERE,"nope.txt")],capture_output=True,text=True)
    assert r.returncode==2 and r.stderr.strip()!=""
