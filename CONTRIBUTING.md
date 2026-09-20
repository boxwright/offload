# Contributing

Issues are welcome, especially **measurements from your own hardware**: run `calibration/` and
`install/preflight.sh`, and open an issue with your GPU, the numbers, and the commands you ran.

For code:

1. `pip install -e ".[dev]"`, then `ruff check src tests` and `pytest`. Both must pass. Tests never touch
   the network, Docker, or your home directory.
2. Keep modules small and readable. One statement per line. No claim in the docs without a file behind it.
3. Sign your commits off (`git commit -s`). By signing off you certify the
   [Developer Certificate of Origin](https://developercertificate.org/): you wrote the change or have the
   right to submit it under the Apache-2.0 license.
