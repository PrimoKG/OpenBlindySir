# Prepare a themed night

Open **Prepare game → Music**, select folders, then use **Build your themed night**.
Shortcuts offer cartoon theme songs, Pop, Rap, French, English, 2012 and the 2010s.
They replace the previous criteria; add further criteria in the lists afterwards.

- **French rap from 2012**: genre Rap, language French, both year bounds set to 2012.
- **Pop or Rap in English**: add both genres, then English as the language.
- **Cartoon themes**: select your themes folder and its shortcut. It proposes
  guessing the series title with 12-second clips.
- **One universe**: add a series, game or anime in Series, games and universes.

Choices within a category are combined with OR; different categories use AND.
Keyword search matches every word, ignoring order, case and accents, across
filenames and metadata. Year bounds are inclusive. Rap also matches Hip-Hop;
languages recognize codes and common labels such as `fr`, French, Français,
`en`, English and Anglais.

Counts and examples use the same filter as the actual round selection. Disabled,
unavailable and offline tracks cannot be played. Overlapping folders count each
track once. Previously heard tracks are excluded unless repeats are allowed.
Give the preparation a name in **Saved selections**, below the filters, to reuse it
in this browser. **Save** persists the settings in the session; **Save and start**
also starts the game.

## Organize the library

**Sources and library search** includes the same shortcuts and genre, language
and year-range filters alongside existing filters. Sort by title, artist, year,
genre or language. Unknown years remain last in both directions. Results stay
paginated and adapt to the viewport.

Outside an active game, **Use these filters for the next game** transfers the
thematic criteria and folder to game preparation. Other browsing filters — file
extension, availability, activation, quality and consumption state — remain
library-only. Disabled and unavailable tracks are always excluded from games.

**Correct track information** edits genre and language without changing the audio
file. Select tracks on the current page to add genres, languages, tags or linked
works in bulk. Bulk additions retain existing categories; use the individual
editor to replace or clear them. The private 15-second preview remains centered
around the track midpoint and consumes no round.

## Missing metadata

An unknown language, genre or year cannot satisfy a filter on that field. A count
identifies tracks needing classification. **Language not set** selects unknown
languages; instrumental music can use `zxx`. The year describes the chosen track
or version, rather than automatically the series premiere. Use verified values;
a folder name does not prove genre, language or year.

Exact recognizable legacy tags, such as Rap or Français, provide a fallback only
when an explicit genre or language list is absent. An explicit empty list blocks
that fallback. Metadata JSON version 3 accepts `genres` and `languages`; versions
1 and 2 remain supported. See [metadata format](media-and-metadata.md).

## Updating

This change uses protocol **11** and snapshot **9**. Back up state, update the
server, Bridge and web UI together, then reload existing browser tabs. Snapshots
1–8 migrate. To return to protocol 10, restore its format-8 backup; older images
cannot read format 9.

File paths determine track identity. Prefer app tags and metadata for organizing
themes: moving or renaming files requires a rescan and reassociating metadata.
