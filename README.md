# Libgen Bulk
### Bulk downloading from Library Genesis with enhanced filtering, robust retrying/backoff, mirror management, and complaince.

This is a cli tool that is useful for highly specific bulk downloads from Library Genesis. It has filtering capabilities that are better than libgen itself, it can preprocess files for use in models, it can run in the background, and more. 

It focuses on **content over files**: you can download exactly one copy of every text in a genre from a particular year if desired, turned into TXT format for ease of use.

## Why not norrent?

Libgen Bulk is superior to torrenting because libgen torrent files contain ~1000 books each. This tool can filter by: genre, subject, publication year, type of file, file size, and many other things. There is even an option to use an LLM to verify downloads and maintain corpus quality. 

#### Benefits:

1. It is easier to **maintain legal complaince**: libgen torrent files are not sorted for compliance natively, creating legal risks, and non-leeching torrenting activity (i.e. seeding) usually qualifies as distribution.
2. It is straightforward to **filter by genre**: libgen has no filtering here besides Fiction, Nonfiction, Academic Articles, etc.
3. **Native preprocessing** is included for use in model training.

For example: as of 2026, under US law, things published prior to 1931 are in the public domain. Torrent files are not sorted by publication year, creating legal risk, but filtering using Libgen Bulk can reduce this risk.

## Disclaimer

It's worth noting that Library Genesis is consistently in hot water for blatant piracy. This project is intended for educational and academic purposes only. I assume no liability for how it is used (see license). It is up to the user to use it properly, legally, and ethically.

#### A note on recent precedents

The below is my personal opinion, not legal advice.

In two pending cases, [Richard Kadrey, et al. v Meta Platforms, Inc.](https://s3.documentcloud.org/documents/25984135/richard-kadrey-et-al-v-meta-partial-summary-judgment.pdf) and [Andrea Bartz, et al. v Anthropic PBC](https://storage.courtlistener.com/recap/gov.uscourts.cand.434709/gov.uscourts.cand.434709.231.0_2.pdf), two separate judges agreed that the highly transformative nature of model training on copyrighted works constitutes "Fair use". This does *not* imply that illegal acquisition or distribution of said copyrighted works through piracy is without legal risk and does not eliminate the chance for different rulings in the future. It does, however, in my opinion, reduce the risk of using libgen for model training. It is up to the user and their counsel to ensure complaince wiht all applicable regulation in their jurisdiction.

