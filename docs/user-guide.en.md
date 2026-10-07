# Using OpenBlindySir — V0.5 — development

[Guide français](guide-utilisateur.md). One server hosts one game at a time, on a
LAN, private VPN or the Internet. Players use a browser without creating an account.
See [hosting](deployment.md) or [Docker](docker.md). Update server, Bridge and web
UI together: **protocol 9**. [Install the Bridge from source](bridge-installation.en.md)
or use Docker today; uvx and release archives require publication first.

Quick access: [join and sound](#join-audio-and-recovery), [host setup](#host-setup),
[library](#sources-search-and-metadata), [finale](#the-grand-finale),
[stop and restore](#stop-and-restore).

## Join, audio and recovery

The host shares a **QR or invitation link** from **Invite players**, or the plain
game URL with the game password. Keep the host password private.
Each Bridge owner receives a separate
[private identity file](bridge-installation.en.md#uvx-and-guided-setup) to keep on
their device; do not share it with players. On a private network, trust the configured certificate first.
With the QR/invitation link, enter only a nickname (24 characters maximum) and
**Join**. The plain URL also asks for the game password. To use the shared session
code, choose **Restore my place**: a new nickname joins directly while registrations
are open; an existing nickname follows host approval below. Test your sound,
confirm the beep, set the volume and keep the browser active.

The **FR / EN** switch stays in every header, from joining to results and host
access. Switching is immediate without reloading, interrupting audio or losing
form drafts. Each browser saves its own preference for future visits. If local
storage is blocked, switching still works in the current tab. Player names,
answers, custom instructions and music information retain their original content.
Audio preferences are also saved locally. **Audio correction (ms)**
ranges from −500 to +500: positive values advance the next playback to compensate
for a delayed output; negative values delay it. For example, try +150 ms for a
Bluetooth output delayed by 150 ms. Changes apply to the next playback and never
change official answer timing or award points. Start at zero and test your output.

The browser cookie resumes your seat automatically within the same session.
**Session code** is shared by everyone. The host can view/change/regenerate it
in **Invite players**, also available in Settings during a game. The QR needs
only a nickname. Rotation invalidates the old code/QR without disconnecting players.

On another browser, **Restore my place** asks for nickname and the shared code.
An existing nickname requires host approval within two minutes. Give the host
the reference displayed on your request so they can distinguish requests for the
same nickname. Approval keeps
points, answers and team, disconnects the old browser and grants player access.
Hosts must elevate with the host password again. Existing-seat recovery works
while new registrations are locked. A recovered MC remains a spectator until
host mode is enabled again. If saving fails, the old access remains valid and
the request can be retried until it expires.

## Continuous game and modal controls

Rounds advance automatically after a two-second intermission, controlled by the
server even when the host tab closes. The last round enters final review. No public
points, other players’ answers or reveals appear before the host presents them in the grand finale. **Pause /
Resume** also pauses an intermission. **Settings** opens without pausing the game;
its Pace tab changes the gap (0–10 seconds) or selects manual advancement. Rules,
scoring weights and selected music folders remain fixed for the current game.

**Prepare game** has Music, Rules, Pace, Players and teams, and Advanced tabs, a
sticky summary and save/start actions. Closing dirty preparation asks to discard
changes. Sound controls have their own modal. Exceptional round actions live in
Settings → Game actions; their confirmations describe what is retained.

**Library sources and search** opens a modal with title/artist/filename/folder
search, Bridge/folder/format/availability/consumption filters, sorting over the
entire catalogue and responsive pages: up to 20 tracks in two columns of ten,
ten in one column, or five per column on short screens. Filters and page survive closing. A playing
host may browse before launch, with a spoiler reminder. Mounted folders, scanned
folders and folders selected for the game are distinct; Docker mounts require
container recreation, while added files in an existing mount only require rescan.

Final review uses title/artist Correct/Incorrect, All correct/All incorrect, and a
signed manual score. Buttons follow the saved scale (title 2 + artist 3 = 5).
Title-only, artist-only and custom modes expose their applicable criteria. Missing
decisions remain unchecked, distinct from incorrect. The custom mode has its own
correct-answer weight; the total scale is at most 1,000 points per round. Scoring
is manual by default. [Optional automatic scoring](automatic-scoring.en.md) recognises
requested title/artist/album/year/featuring in one field, with a default 90% threshold
adjustable from 80 to 100%. Uncertain cases require review. Manual overrides are identified.
Review offers **Show rounds with missing point awards** and batch zeroing absent answers,
without zeroing captured drafts. Saves await the server echo; concurrent stale
corrections are refused. Published recaps retain criterion decisions.

Final corrections accept an optional reason (120 characters): amount and reason
save together, remain private until publication, then appear in results/history
and CSV/JSON exports. Reset clears both. Track-information corrections apply to
all games in the session, including after a reserve reset; they do not change
music files or already published archives. Search uses corrected title/artist.

Teams lead the podium, provisional totals and history when teams are defined.
Individual standings remain available; unassigned players stay there and ties
share a rank. After results, **New game with remaining tracks** keeps consumed
exclusions; **Restart with the entire library** resets only those exclusions.
Both retain players, teams, settings, metadata and archives. A cancelled allocated
round consumes its track even before playback; mere prefetch does not consume it.
Private replay advertises full-listening permission before clicking and gives
specific recovery messages for offline Bridges, changed sources and browser blocks.

## Play rounds

Wait for preparation, loading and countdown. Type a free-text answer and choose
**SUBMIT**, or Enter. Submission is final for that round: wait for the saved
acknowledgement. Unsubmitted text is a synchronized draft. When answers close,
the latest received draft becomes **Captured draft**, without official rank or
submission elapsed time. In automatic mode it is assessed on closure when the captured-answer policy permits; the zero policy enforces zero.

Audio ending does not necessarily close answers. The host can pause audio and
answers, resume together, replay, add time or close. Paused time is excluded from
answer elapsed time. After each round, answers are saved and the host moves on.
**The host reveals tracks, closed answers and provisional points during the grand finale.**
The anonymous answered counter is hidden when fewer than three players are expected.

## Host setup

Open `/host` or Host access and enter the host password. **Host player** participates
with the same anti-spoiler rules; **MC** does not play and can see upcoming tracks
and live answers. Switching to MC is allowed between rounds; switching back to
player waits for the next game. Spectators listen and see results without answers,
scores or readiness requirements.

Select folders, round count, clip duration, answer grace period, instructions and
scoring expectations. Parent/child selections do not double-count tracks. **Save
and start** applies settings atomically. If there are too few fresh tracks, reduce
rounds or allow repeats. Favorites are saved in this browser. Advanced options
include volume normalization, silence avoidance and folder balancing. Balancing
rotates shuffled folder groups without duplicating tracks; selecting the root uses
each track's containing folder. In MC mode, choose a track for a numbered,
unprepared round and confirm the choice; its launch stays explicit even with auto-start.

Assign teams and spectators in the lobby. Team totals sum individual points.
**Close registrations** blocks new identities, while reconnection/recovery remains
possible. The host can reopen registrations in any phase. Invitations contain the
URL only: share the game password separately.

## Sources, search and metadata

Three distinct choices: the locally authorized root or Docker mount, subfolders
scanned by a Bridge, and folders selected for a game. **Library sources and search**
adds/removes relative subfolders and requests a rescan. An empty root path includes
everything; remove that root before limiting the scan to individual subfolders.
Changes are asynchronous: folder controls remain disabled until the Bridge's
completed scan is received. Counts and folders update automatically. If the scan
is not confirmed within 75 seconds, refresh the library and retry. Up to eight
different Bridges can stay connected, with persistent, distinct UUIDs.

An outside directory requires a local root choice or a read-only Docker mount.
Recreate only the Bridge after changing its mounts; retain the server/session
volume. Adding files under an existing mount only needs a rescan. Symlinks,
junctions, absolute paths and traversal are refused. Inaccessible scans keep the
previous catalogue and display instructions. See [Docker source management](docker.md#sources-dynamiques-et-réécoute).

Search filename, relative folder, imported/corrected title or artist. Filter Bridge, relative
folder, extension, availability and fresh tracks; pages adapt to the viewport: 20 matches in two columns of ten on wide screens,
ten on narrow screens, five per column when height is limited. Sorting by title, artist, filename or folder applies to the entire catalogue
before pagination. Filters and the page survive closing the modal. Folder search preserves ancestors for navigation. This data is host-only
in lobby/final review/results, or available to MC during play.

MP4/MOV/MKV/AVI and other whitelisted containers provide **only their first audio
stream**, regardless of default-stream flags. Video, subtitles, data, artwork and
musical tags never enter clips. Missing audio gives a private `NO_AUDIO` diagnostic
and the game tries another track. Production output remains AAC/M4A 128 kbit/s,
48 kHz stereo: roughly 320/400/480 kB for 20/25/30 seconds plus container overhead.
Opus/WebM is configurable. DRM files and codecs missing from FFmpeg are unavailable.

Optional metadata is UTF-8 JSON `{version:2,rows:[...]} (version-1 imports remain supported)`, keyed by Bridge UUID
and exact NFC POSIX relative path including extension. Title, artist, featuring,
album and year are optional. Export a template first. Imports are limited to
1 MiB/10,000 rows; invalid, duplicate, unknown and ambiguous rows are reported
individually while valid rows are accepted. Non-empty manual corrections take
priority per field over imports, then title/artist tags or a cleaned filename.
Clearing a manual field restores its fallback. Corrections/imports persist in
the private snapshot; exports merge them for still-known files. Detailed format:
[technical notes](v0.2.en.md) and [source reference](media-and-metadata.md).

### Private previews and categories

**Preview 15 s · middle of the track** starts a private midpoint segment beneath the
chosen track. Stop it immediately or close/change page. Short files use their
available duration. It never consumes a track or broadcasts public PLAY.
If the browser cannot decode the segment, retry with the preview button: a faulty
segment is downloaded again. An autoplay block keeps the segment for the next attempt.
Metadata editing opens beneath the chosen card and guards unsaved changes.

Disable/reactivate tracks without deleting files/history. Disabled tracks leave
future draws and unprepared manual plans; existing prepared excerpts remain intact.
Filter active/disabled tracks, multiple tags and **Linked to** associations.
Use comma-separated genres/eras/languages or games/anime/films. MC can filter a
theme and choose its numbered rounds. Selecting page cards allows batch category
addition/activation changes, retaining existing labels and reporting success counts.

## The grand finale

The last round opens **The grand finale** for everyone. Ending early can finish
with the current awards and open the replay/end-session menu; see
[Stop and restore](#stop-and-restore). During the finale, the
host privately selects a played round, then uses **Present round N** to present its
track and closed answers. Players follow confirmed point changes and provisional
rankings live. Private navigation never changes the public scene.

The persistent action bar names the exact round to present and explains what remains
before the podium. The preparation selector is separate from the public scene.
**All rounds** opens detailed navigation and search. Missing answers occupy compact
rows with an explicit zero-confirmation action and optional manual exceptions.
Players who were not eligible for that round are not counted as missing answers.
The expected answer shows missing title/artist information before scoring.
The latest public award includes confirmed zeros as well as positive points.

The finale sound preference is in **Sound**, uses the existing volume and requires
audio activation. Cues never interrupt a replay. Confetti respects reduced motion;
the detailed results appear before the actions for starting another game.

**Test my audio** stays available during the finale and in the **Sound** menu.
If the phone suspends sound, use **Tap to re-enable sound**, even between replays.
An ongoing shared excerpt resumes at its current position; an ended excerpt is
not restarted. Check the volume and the phone's selected audio output as well.

The shared totals count revealed rounds and final adjustments. Revisiting a round
does not add its points again. Pending, partial and checked decisions have separate
states; players see their total and the current round’s points. Team totals are shared.
**Listen together** synchronizes the original game excerpt for everyone; **Stop replay**
also cancels pending preparation. When the shared excerpt ends, private playback
becomes available automatically. It is directly beneath the track; track editing
remains in a secondary panel.
The review shows track context, each participant's answer/status, official time
and rank when present, server reception time, and known late audio. Missing data
shows “—”. Removed players who participated remain reviewable.

Use weighted Correct/Incorrect criteria, All correct/All incorrect, or a signed
manual integer between −1000 and +1000. Explicit
zero marks a checked decision; default zero stays unchecked. Enter/blur sends
the value: wait for **Saved**. Navigation and final validation wait for the server.
Saved points survive refresh/reconnection and snapshots; unsent local text can be lost.
Correct title, artist, featuring, album and year before publication.

The host’s detailed totals combine all included rounds and optional final corrections.
Team totals sum individual totals. Captured-draft policy is either manual scoring
or mandatory zero, checked explicitly. Resetting final corrections preserves round
points. Final validation asks for confirmation with totals and unchecked count;
confirming unchecked rows keeps their current values, initially zero.
Correction shortcuts and resets also wait for the server's saved values before
another edit or final publication is allowed.

Once all heard rounds have been revealed, **Start the podium** publishes once and
freezes the journal. The podium reveals third, second and first place in shared
server time, with ties revealed together. Reconnecting resumes the current step;
restored results show immediately. Standings, tracks, answers, timing and recap follow.
CSV/JSON exports use those published results; CSV cells are protected from formulas.

### Scoring and ranking scroll

Each scoring list scrolls independently. Automatic scrolling advances after a
server-confirmed award to the last visible row, including zero, using this device’s
viewport. Active inputs/manual scrolling suspend movement; the next pending player
button resumes it. Rankings show at most five rows, fewer on short screens, with
scrolling and a shortcut to your position.

## Private listening

**Play** fetches the exact game clip on demand. Pause, progress, duration, seeking
and volume belong to a separate host player and never control other players.
**Listen to full track** requires the Bridge owner's local opt-in:
`--allow-full-review` or `OPENBLINDYSIR_BRIDGE_ALLOW_FULL_REVIEW=true`.

Full mode is labelled clearly and can return to the game excerpt. Audio is
reencoded on demand in segments of at most 30 seconds; seeking requests a short
segment. Loading may interrupt between segments. The full source stays on the
Bridge, and segments are not stored durably on the server. Changing rounds cancels
the request and releases the previous Blob. An offline Bridge, changed source or
an exact clip no longer reproducible after restart displays a retryable error;
retry keeps the requested listening position. A lost Bridge or rejected upload
ends the pending transfer promptly. Scoring remains available.

## Stop and restore

**Stop game** during play or the finale offers to return to scoring or finish
with the points already awarded. Finishing stops audio, preserves answers/drafts
and awards, publishes once and opens the replay/end-session menu immediately.
Pending awards retain their current value, initially zero. Remaining presentations
and podium animation are skipped.

**New game with remaining tracks** keeps players, teams, metadata, settings, archives
and consumed exclusions. **Restart with the entire library** clears only those musical
exclusions after confirmation. Removed identities are discarded while their archived
results remain readable. **End session** revokes sessions/codes and resets players/current game,
while saved archives and library metadata remain. Keep private snapshot backups.

Snapshots restore answers, points, configuration, sources, metadata and the last
50 completed games. RAM audio is lost. An interrupted open round closes/captures
answers and displays a warning; a future countdown returns to preparation.
Bridge reconnection regenerates required clips. Snapshot-write failures alert hosts.

## Troubleshooting and limits

Joins are limited to 60/IP/minute and 600/server/minute, including correct passwords:
wait a minute after `rate_limited`. `MAX_PLAYERS` still caps simultaneous players.
State retains at most 1,000 identities, including removed players needed for current
results. At that cap, `game_full` refuses new joins; New game after archiving or End
session frees previous identities.

In MC mode, **Library sources and search → Choose tracks (MC)** lets the host
choose a numbered round before preparation. Search/filter results show source,
folder, filename, available title/artist, format, measured duration, availability,
played/reserved state. Select a round, choose a track, and wait for server
confirmation before starting. Pending edits disable launch; concurrent revisions
are rejected. The chosen source must belong to the game's selected folders.

Manual choices obey repeat rules, bypass random folder balancing, and cannot
duplicate another round's reservation. Preloading one/two rounds locks choices
as soon as preparation is requested; plan in the lobby or choose a later free
round. A manual ready round waits for explicit launch even with auto-start on.
If the source/Bridge fails, replace it, return to random, skip or end; no silent
substitution. Players and a playing host never receive future choice details.
See [troubleshooting and recovery](operations.en.md).

Retry audio, check volume/output, reactivate after autoplay suspension, and keep
the tab active. Reconnection restores only server-received drafts. “Open elsewhere”
allows taking over the current tab. If a folder is missing, check the mount rather
than entering an absolute path. Review skipped-file diagnostics and codec/audio
availability. Preserve TLS verification and prepare certificate trust correctly.

The project is still in development. Synthetic headless tests do not validate
physical sound or acoustic synchronization. Try actual Safari/iPhone/Android
devices before a game night. See [test records](DEVLOG.md) and [manual checks](testing.md).

## Private Bridges and V0.5 history

Each Bridge has a stable UUID, a name and a distinct secret. The host issues a
private identity file; the owner keeps control of the music root and full-listening
opt-in. See the [V0.5 commands](v0.5.en.md). The Bridges panel shows per-owner
connection, capabilities and errors, and can revoke one identity with confirmation.
During play, host players cannot access source names, the library or archives;
the MC retains private access. An unprepared random pick waits at most 45 seconds
for its owner, then tries another available source. Manual picks offer explicit
replacement, random fallback, skip or end. A prepared excerpt can keep playing.

After final validation, **History** loads retained games on demand, including the
original names and teams, settings, answers, timings, reveals and corrected scores.
Later library changes and games do not modify these records. Hosts can inspect,
export, delete one or purge all with confirmation. Retention: 50 games, 90 days,
16 MiB, without audio. A save warning identifies unavailable durable storage.
Deletion removes the archive from both managed snapshots; exported files and
external backups need separate cleanup. Current final results remain visible until
New game or End session.

Skip links, keyboard controls, Escape/cancel with focus restoration and labelled
audio controls are available. Automated checks cover 320 px and text at 200%.
NVDA/VoiceOver and physical devices still require manual acceptance; this is not
an accessibility certification.

## Automatic scoring and trusted local HTTPS

The [automatic scoring guide](automatic-scoring.en.md) covers aliases, frozen
references, explicit regrading and waves of awards during the shared finale.
Points stay private during answer entry. For phones on the LAN, follow the
[local certificate trust guide](local-certificate.en.md). LAN hosting remains available.

## Finale corrections and reference preparation

On wide desktop screens, the music context sits to the left of scoring and the standings remain on the right. Lists adapt per browser; standings show at most five people. Manual scrolling pauses automatic progression without clearing the preference; **Resume scrolling** enables it again. Buttons remain keyboard accessible with a minimum 44 px target.

Automatic scoring displays the frozen reference actually used during the round, even when track information has since changed. **Regrade** uses the new reference and preserves manual corrections. Captured drafts under the host-decision policy receive suggestions only, with no automatic points. Unknown extra numbers cannot win a numeric title. Similarity thresholds apply separately to each criterion; years require an exact match.

Cards show reasons for pending decisions. The host can undo the last saved correction while its revision has not changed on another screen. Before the podium, completing pending scoring is the primary action; publishing current scores with unchecked answers requires an explicit action. Games with no points are announced as finished. The guide covers reveal, optional listening, points, standings and the next round. Fast pace and animation preferences are stored per browser; muting and reduced motion are respected.

The library opens on tracks and refreshes data each time it opens; source management remains in advanced tools. Quality filters identify ready and missing references for the current criteria, and the selected-source filter limits the correction queue to chosen folders. Automatic scoring does not invent missing references from filenames. **Inherit** uses source values, **Replace** enters a confirmed value, and **Clear reference** blocks imported/audio tag fallbacks. Conflicting edits are rejected while the local draft is retained. Activation and bulk changes are also protected: a batch stops at the first conflict, reports how many tracks were saved and keeps the explanation visible. Refresh, compare and retry the remaining entries.

Export produces ZIP packs of JSON files limited to 1 MiB and 10,000 rows. Each pack is bounded to 8 MiB and 10,000 rows. **Download next pack** completes larger collections; packs are independently importable without filesystem extraction. Legacy JSON imports keep their 1 MiB limit. Encrypted members, arbitrary paths and compression other than stored/Deflate are rejected.

A permanently closed audio context can be recreated after a user gesture. Obsolete requests, replaced sockets and unmounted controllers are cleaned up. An old track's failure cannot replace the current playing state. Private and shared playback use the browser's volume. Audio testing and recovery remain accessible during the finale.
