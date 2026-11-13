# Sieve demo video

A 72-second motion-graphics video built with [Remotion](https://www.remotion.dev), in the NEAR Hackathon's visual style. Every number, score, signature and transaction in it is read from the live testnet deployment.

```bash
npm i
# with the Sieve API running locally (python -m uvicorn --factory sieve.api:main --port 8791 from the repo root):
../.venv/bin/python scripts/fetch_data.py http://127.0.0.1:8791   # scores, signatures, DAO ids -> src/data.json
npm run capture                                                    # page screenshots -> public/shots
npm run dev                                                        # preview in Remotion Studio
npm run render                                                     # out/sieve.mp4
npx remotion still Banner ../assets/banner.png                     # README banner
```

`src/verify.json` holds the output of `sieve verify` shown in the last scene.
