# CareerPick cardnews offline generator

Run only with verified official notice data. No publishing or production workflow changes.

1. `pip install -r requirements.txt`
2. `python validate.py verified.json`
3. `python generate.py verified.json output`

Output: 1080x1350 PNG cards, source.json, captions.txt, cardnews.zip. Requires 3–8 cards and a Korean font. `verified: true` means **human checked**; the program does not verify factual accuracy. Review every output before posting. No automatic publishing.
