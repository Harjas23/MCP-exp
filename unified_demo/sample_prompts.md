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
I uploaded my business records. Before calling the business enrichment tool, obtain my permission with: “Each matched record will consume 1 credit; non-matches consume no credits. Do you want me to proceed?” Only after I approve, pass my uploaded rows to the tool and enrich all matched rows. Do not show match or non-match counts at the beginning.
```

```text
I uploaded my consumer records. Before calling the consumer enrichment tool, obtain my permission with: “Each matched record will consume 1 credit; non-matches consume no credits. Do you want me to proceed?” Only after I approve, pass my uploaded rows to the tool and enrich all matched rows. Do not show match or non-match counts at the beginning.
```

```text
I uploaded my contact records. Before calling the contact enrichment tool, obtain my permission with: “Each matched record will consume 1 credit; non-matches consume no credits. Do you want me to proceed?” Only after I approve, pass my uploaded rows to the tool. Enrich all matching contacts, including secondary contacts, without showing match or non-match counts at the beginning.
```

## Credit tests

```text
Reveal 25 records.
```

When the paid account has fewer credits, the server must return records immediately up to the remaining credit balance, explain why fewer records were returned, and include the top-up link. Do not ask permission again.
