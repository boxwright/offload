# Questions people ask

**Is this allowed with a Claude subscription?**
Offload runs Claude Code in its documented print mode, on your own machine, with a token you create yourself
with `claude setup-token`. Anthropic's documentation describes that token for scripts and other non-interactive
use on Pro and Max plans, and says such use draws from your plan's usage limits. One person, one account, your
own hardware. Offload never shares an account, pools accounts, or resells access. Terms change; read them
yourself. Offload is not affiliated with or endorsed by Anthropic.

**So what do I actually save?**
Usage against your plan's limits. On our jobs the paid model worked for seconds while the local model worked
for minutes (see the table in the README, and the reports under `jobs/`). The dollar figures Offload prints are
what the same calls would cost at API list prices. They are a yardstick for pacing, not a bill.

**Why not just point Claude Code at my local model for everything?**
You can. Offload's bet is different: a strong model is worth its cost for three short moments (the plan, the
review, a rescue when the local model stalls) and a waste for the typing in between. The reports show when a
rescue happened, so you can judge that bet on your own work.

**What hardware do I need?**
An NVIDIA GPU with 24 GB of VRAM or more, 32 GB of RAM, Linux, Docker. A 32 GB laptop is not a practical host;
we measured one and wrote down why. See [hardware.md](hardware.md). Run the preflight script before anything else.

**Which local model?**
Qwen3.8-27B (Unsloth GGUF build, Apache-2.0), served by llama.cpp. It is the only model we have measured.
The proxy speaks to any OpenAI-compatible server, so others will work mechanically; whether they code well
enough is a measurement nobody has done yet. More models are planned.

**Does my code leave my machine?**
The local worker sends your code to the model on your own GPU. The paid worker sends what it reads to
Anthropic, the same as using Claude Code by hand: the plan step reads the repository, the review step reads
the diff and a few files. If a repository must never leave the machine, do not give it to Offload, or any
cloud model.

**What happens at a rate limit?**
The daemon reads the reset time from the message and parks the job until then. After that time the job continues
in the same Claude session. You are not notified. The limit belongs to your account, so no other job calls
Claude before the reset time. Work that does not need the paid model continues.

**Can it run on a Mac or on Windows?**
Not as the host, today. A laptop can drive a Linux box over SSH with the `offload-remote` wrapper.
