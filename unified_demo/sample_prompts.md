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
I uploaded my business records. Use the business enrichment tool on my uploaded rows. First tell me how many records match and how many do not match, then ask how many matched records I want to enrich. Do not enrich until I provide the number.
```

```text
I uploaded my consumer records. Enrich only my uploaded data. First return matched and non-matched counts, then ask for my permission by asking how many matched records to enrich.
```

```text
I uploaded my contact records. Enrich all matching contacts, including secondary contacts. First return matched and non-matched counts, then wait for my requested count before enriching.
```

## Credit tests

```text
Reveal 25 records.
```

When the paid account has fewer credits, the server must return no records first and offer the available count or top-up link. If the user then says `go ahead with the available number`, call the same tool again with that count.
