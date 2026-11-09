"""Vercel entry point: the read-only Sieve API. The static page in web/ is served by Vercel directly."""
from sieve.api import main

app = main()
