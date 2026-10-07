# Automatic scoring and grand finale

[Français](notation-automatique.md). V0.5 development, protocol **9**, snapshot **7**.
Update the server, web UI and Bridge together. Older sessions keep manual scoring;
existing scores are not recalculated during migration.

## Configure the rules

In Settings → Rules, select **Scoring → Automatic, with host corrections**.
Manual mode remains available. Existing title, artist and title-and-artist modes
remain; **Information to recognise** lets the host select title, artist, album,
year and featuring, with a separate weight for each. The total is capped at
1,000 points per round. Free-form custom instructions remain manually scored.

Players use **one text field**, in any order. The default limit is 1,000 characters;
`ANSWER_MAX_CHARS` accepts 20–1,500 and the server publishes the effective limit
to browsers. The protocol hard limit is 1,500 characters.

The default acceptance threshold is **90%**, adjustable from 80 to 100%. It applies
to **each criterion**, not to the average answer. Successful criteria earn their
configured points; a correct title cannot compensate for an incorrect year.

## Matching and limitations

Local matching ignores case, accents, punctuation and word spacing. It identifies
candidate fragments and computes `100 × (1 − distance / maximum length)` using
Damerau–Levenshtein distance. Insertions, deletions, substitutions and adjacent
letter transpositions each cost one operation. Similarity is not a probability
that an answer is correct. No external AI service receives answers.

- At or above threshold: award the criterion automatically.
- Up to ten percentage points below threshold: request host review.
- No sufficient match: no automatic point for the criterion.
- Missing reference: require host review for that criterion.
- Years require an exact four-digit match; several proposed years are ambiguous.
- References or aliases of three characters or fewer require an exact match.
- Overlapping fragments for different references and explicit alternative guesses
  require review. Identical references may share a fragment.

With title “Sapés comme jamais”, artist “Maître Gims”, year 2015 and album
“Pilule bleue” (or an explicitly accepted album alias), this single input succeeds:

```text
Sapéscomme Ja m ais Maitre Gims 2015 ft niska   pilule bleue
```

All four criteria reach 100% after normalisation: four points at one point each.
Niska also matches when featuring is requested; an optional `ft Niska` clause
does not penalise the answer when Niska is a known featuring reference or alias.
“Sapés comme jamias” reaches 93.75%: accepted at 90%,
review required at 95%. Complex ambiguous answers may need host review.

## References, aliases and corrections

In the library, open **Correct track information → Accepted variants**. Enter one
alias per line, up to eight per title, artist, album or featuring, each at most
256 characters. Use only genuinely equivalent names/titles/album editions.
Aliases travel with version-2 metadata JSON imports and exports:

```json
{"artist": ["Maître Gims", "Gims"], "album": ["Pilule bleue"]}
```

After saving the settings, the lobby reports selected tracks whose known references
are incomplete. File tags may only become available after preparing the excerpt.
A filename alone is not a trusted automatic title reference.

Rules, weights, threshold, references and aliases freeze when playback first starts.
Library edits do not silently regrade a round. In the finale, edit references and
select **Recalculate this round with the new references** for an explicit regrade
of that round only. Manual overrides are preserved. Already revealed points can
change. Host-only evidence shows the reference actually used, matched fragment,
percentage, threshold and review status; an override retains the earlier analysis
with an **Overridden by the host** label.

## Private scoring and shared reveal

Locked answers are graded on the server when received. Captured drafts are graded
on closure; the `zero` policy gives unlocked answers zero. Absent answers are
confirmed at zero. Answer acknowledgements contain no correction or points.

**Present round** reveals the track and answers. For automatically graded rounds,
points arrive in waves of three players: after 1.5 seconds, then every second.
Standings contain only revealed points. The host can **Reveal all points now**.
Moving to another round completes the previous wave; going back does not repeat
awards. Manual changes appear live. Rank improvements and matched criteria are
shown, with position animation; negative corrections do not play the award sound.
Animations respect reduced-motion preferences.

Shared replay, private listening, optional sound effects and **Test my audio**
remain available. Normal podium launch waits for an active wave to finish;
**Stop game** can still end with current points. Reconnection and snapshots preserve
scores, rules and reveal progress. Final validation writes the definitive journal once.

Comparison has a deterministic work budget; excessive complexity requires host review instead of an arbitrary rejection. Exact references are still searched throughout the bounded field.


## Matching safeguards after the audit

The matcher allocates compatible fragments across criteria (up to 4,096 combinations).
A repeated artist name can use a separate occurrence instead of colliding with the title.
Slashes, semicolons and pipes may separate correct fields; explicit “or/ou” alternatives
remain subject to review. A number already recognized as a title or album, such as
“1989”, does not count as an additional release-year guess.

Multiple known optional metadata fields can appear together. An optional `ft Niska`
clause is accepted when Niska is a known featuring reference or alias. The `ft` prefix
never exempts arbitrary names or extra guesses. An incorrect or missing requested year
does not exempt unrelated extra words from review. Without a known featuring reference,
the host reviews the clause.

Filename display fallbacks never become automatic references, including on explicit
regrading. JSON version 2 exports preserve aliases so export/import round trips retain
accepted variants. These fixes apply to new evaluations; updating does not recalculate
existing evidence or replace manual corrections.
