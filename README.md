# Libgen Bulk
#### Bulk downloading from Library Genesis

This Python cli tool is useful for specific bulk downloads from Library Genesis. It has filtering capabilities that are **better than Libgen itself**, it can preprocess files for use in models, it can run in the background, and more. 

It focuses on **content over files**: you can download exactly one copy of every text in a genre from a particular year if desired, turned into TXT format for ease of use.

## Why not torrent?

Libgen Bulk is superior to torrenting because libgen torrent files contain ~1000 books each. This tool can filter by: genre, subject, publication year, type of file, file size, and many other things. There is even an option to use an LLM to verify downloads and maintain corpus quality. 

### Benefits:

1. It is easier to **maintain legal complaince**: libgen torrent files are not sorted for compliance, creating legal risks, and non-leeching torrenting activity (i.e. seeding) usually qualifies as distribution.
2. It is straightforward to **filter by genre**: libgen has no filtering here besides fiction, non-fiction, academic articles, etc.
3. **Native preprocessing** is included for use in model training.

### For example: 

If you want to download every math textbook published prior to 1931, the lastest year whose works are public domain, this is possible with Libgen Bulk. This can facilitate math-specific model training. 

Libgen itself can search for specific years, but it can't search a specific genre like "math textbooks".

## Disclaimer

It's worth noting that Library Genesis is consistently in hot water for blatant piracy. This project is intended for educational and academic purposes only. I assume no liability for how it is used (see license). It is up to the user to use it properly, legally, and ethically.

### A note on recent precedents

The below is my personal opinion, not legal advice.

In two pending cases, [Richard Kadrey, et al. v Meta Platforms, Inc.](https://s3.documentcloud.org/documents/25984135/richard-kadrey-et-al-v-meta-partial-summary-judgment.pdf) and [Andrea Bartz, et al. v Anthropic PBC](https://storage.courtlistener.com/recap/gov.uscourts.cand.434709/gov.uscourts.cand.434709.231.0_2.pdf), two separate judges agreed that the highly transformative nature of model training on copyrighted works constitutes "Fair use". This does *not* imply that illegal acquisition or distribution of said copyrighted works through piracy is without legal risk and does not eliminate the chance for different rulings in the future. It does, however, in my opinion, reduce the risk of using libgen for model training. It is up to the user and their counsel to ensure complaince wiht all applicable regulation in their jurisdiction.
