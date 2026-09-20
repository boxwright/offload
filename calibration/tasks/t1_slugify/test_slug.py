from slug import slugify
def test_basic(): assert slugify("Hello World") == "hello-world"
def test_punct(): assert slugify("  Hello,   World!!  ") == "hello-world"
def test_accents(): assert slugify("Crème Brûlée Ñandú") == "creme-brulee-nandu"
def test_digits(): assert slugify("Version 2.0 (beta)") == "version-2-0-beta"
def test_empty(): assert slugify("!!!") == "n-a"
def test_unicode_other(): assert slugify("日本語 test") == "test"
