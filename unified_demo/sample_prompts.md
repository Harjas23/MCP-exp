# Sample prompts

Copy these prompts into Claude after signing in through the unified demo login page.

## Paid search and purchase

```text
Find me Starbucks in Ohio. Show all 10 masked samples, total matches, and insights. Then ask how many records I want to reveal.
```

```text
Find me contacts working as managers. Show the 10 masked samples and insights, then let me choose how many records to reveal.
```

```text
Find me consumers with income of more than 20K. Show the 10 masked samples and full-result insights, then ask how many records I want to reveal.
```

## User-owned enrichment

Upload one of the sample CSV files in Claude and use:

```text
I uploaded my business records. Use the business enrichment tool only on my uploaded rows. Ask permission to proceed without showing match or non-match counts. After I give permission, enrich all matched rows and return the records with total credits deducted and remaining.
```

```text
I uploaded my consumer records. Enrich only my uploaded data. Ask permission to proceed without showing match or non-match counts. After I give permission, enrich all matched rows and return the records with total credits deducted and remaining.
```

```text
I uploaded my contact records. Enrich all matching contacts, including secondary contacts. Ask permission to proceed without showing match or non-match counts. After I give permission, return the enriched records with total credits deducted and remaining.
```

## Credit tests

```text
Reveal 25 records.
```

When the paid account has fewer credits, the server must return records immediately up to the remaining credit balance, explain why fewer records were returned, and include the top-up link. Do not ask permission again.
