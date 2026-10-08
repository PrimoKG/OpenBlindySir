# Recorded test analysis — 8 October 2026

**The finale does not meet the standard described in the previous delivery reports.** A confirmed layout defect makes names and answers unreadable. The pre-start reference check misses edited settings. Several controls and status messages obscure what the host is doing. Passing automated suites did not establish that the complete experience was working well.

This is an **analysis, not a fix delivery**. The findings remain open. No production container, volume, music file or session state was changed. A temporary CSS change was tested only in an isolated synthetic page to establish a cause. The [full French report](2026-10-08-test-video.md) contains the detailed findings and acceptance criteria.

## Evidence and limits

Local recording: **2026-10-08 20-06-24.mp4**, 8:34.63, 1920 × 1080 at 60 fps. The whole timeline was examined using overview frames and denser transition sequences, with individual frames around critical actions. Visual timestamps are approximate to one second.

Workspace code was inspected at **22c6f6e9c21e7d6c9b7d28179e666d84211359e7**. The video does not display a served bundle identity; the code corroborates the findings rather than proving the recorded version. The CSS experiment used the real stylesheets, installed Chrome, synthetic HTML and a blocked network, at viewport widths of 1280, 1366 and 1920 px.

The entire encoded audio track is silent: mean and maximum volume **−91 dB**, silence detected from 0 to 514.60 s. Visible playback warnings can be assessed; what players actually heard cannot. Player phone screens are not recorded. Private frames, logs and scripts stay under **.local/video-audit-20261008-200624/** and are excluded from Git.

P1 means a major usability failure; P2 means an important interaction or comprehension problem. These are not security severity ratings.

## Findings

| ID | Priority | Time | Finding and required direction |
| --- | --- | --- | --- |
| V01 | P1 | 06:39–08:18 | Names and answers wrap one character per line. The desktop override changes grid columns without resetting the two-column named areas. An implicit scoring column consumes the available width. The isolated fixture measures 0 px for the name/answer columns and an 841 px card. Resetting the areas restores usable width in that experiment. Fix the complete grid and verify readable content with five criteria and long evidence. |
| V02 | P1 | 06:48–08:18 | Oversized cards also defeat automatic scrolling: ScoreScroll only remembers fully contained rows, so no row can trigger the next batch when every card is taller than its pane. Repair V01 and define an oversized-card fallback. Manual-scroll pause is a separate, intentional state, not proof that the preference checkbox is broken. |
| V03 | P1 | 05:13–05:22 | Missing-reference warnings are hidden whenever setup is dirty. Their count describes saved settings, while selection preview carries sources and filters without the draft scoring criteria. Recompute readiness for the actual draft before direct save-and-start; offer actionable preparation, compatible-track selection or explicit manual fallback. |
| V04 | P1 | 06:48–08:04 | Several tracks have display titles but no usable scoring references; others lack album, year or featuring. The scorer correctly refuses to invent a reference from a display filename and leaves unknown criteria pending. The app nevertheless presents automatic scoring without preparing the data needed to fulfil that promise. Expose trusted references, clean confirmed metadata and aliases, and distinguish unknown featuring from a verified absence. Changing the 90% threshold would not solve missing data. |
| V05 | P1 | 00:53–01:05 | The first round's answer timer runs while the host browser reports blocked audio. Save-and-start does not unlock the host audio engine during that user gesture. Prepare local audio before the countdown and provide clear readiness and recovery. Verify the full fresh-browser flow with native autoplay policy and physical phones. The recording cannot prove later audible playback. |
| V06 | P2 | 03:14; 07:55–08:18 | The audio-test button exists in the header but scrolls out of view during scoring. Keep a compact local test/recovery action accessible at the point of use, with private replay, shared replay and sound effects clearly distinguished. |
| V07 | P2 | 00:00–00:51; 05:13–05:22 | A saved cartoon/series instruction persists into a five-criterion pop/rap setup. Persistence itself is intentional, but the summary does not expose the mismatch. Review instructions when themes or criteria change; preserve custom text and show a coherent final configuration summary. Improve desktop use of the setup modal. |
| V08 | P2 | Both games | Keep the requested single answer field, but help players understand the active criteria, points and flexible input format near that field. The generic form and host-only explanation do not provide enough guidance under time pressure. Make submitted and captured draft states clear in both languages. |
| V09 | P2 | Both finales | Large scene, navigation and audio blocks push answers below the fold; the scoring column is cramped while other space is underused. Page scroll and inner scroll compete with a fixed action bar. Prioritise readable answers and decisions; compact references/audio; adapt to actual card width and viewport height. Three columns are not a success criterion by themselves. |
| V10 | P2 | 02:41–04:31 | The five-step guide looks like controls but consists of noninteractive list items. Its active-step calculation never selects the ranking step. Implement genuine accessible actions or clearly passive progress indicators whose states reflect the flow. |
| V11 | P2 | 03:49–04:25; 08:13–08:18 | Private selection and public presentation are separate but hard to follow. Present/re-present/next share ambiguous labels and a changing button location. Show both contexts persistently and label the exact destination. At 04:23 round 1 is correctly presented before round 4: this passage does not prove a navigation failure. |
| V12 | P2 | 04:31–04:58; 08:03–08:21 | All rounds can be revealed while many answers remain unreviewed. The podium dialog's main action says to finish awards, but only returns to scoring; repeated openings do not help users complete the work. Name the actual action and target a pending response. Keep incomplete publication an explicit secondary choice. |
| V13 | P2 | 08:17–08:18 | The manual title decision correctly grants +3, but response-level progress remains unchanged because four criteria are unresolved. Show awarded points, decided criteria and fully reviewed answers separately rather than leaving users unsure whether the action worked. |
| V14 | P2 | 03:14; 08:18 | Saved means no pending write, even with undecided answers. It can be read as completion. Separate acknowledgement of a saved change from the actual scoring progress and failure state. |
| V15 | P2 | 05:01; 08:21–08:29 | The zero-score ceremony still uses first-place cards, confetti and a victory cue in code, while repeating the no-score message. Incomplete publication is also not clearly distinguished from a fully reviewed game with no correct answers. Persist and display completeness; adapt the ceremony to incomplete, complete-with-zero and actual winning results. The cue cannot be heard in the silent recording. |
| V16 | P2 | 05:01–05:10; 08:25–08:34 | Restart/session actions are below ceremony and result details, requiring another search and scroll. Bring useful post-game choices close to the ceremony and keep repeated details/exports secondary. The restart menu is observed working. |
| V17 | P2 | Both finales | Shared replay, point waves, ranking activity and the ceremony exist, but administrative correction dominates the host's experience. Data readiness and readable decisions must come before spectacle. Build a clear reveal → response → confirmed points → ranking movement → next-round flow; validate it simultaneously with a host and several real player devices. |

## Findings that the evidence does not support

- No demonstrated loss of points: the manually awarded +3 reaches the second podium. The first zero result follows explicit publication with 15 pending responses.
- No demonstrated general similarity-threshold failure: missing references and the manual policy for captured drafts account for several pending states. This recording is not a labelled matcher benchmark.
- No demonstrated wrong round count: setup ends at five rounds, and five are played.
- No demonstrated failure of restart or late-round return: restart is visible around 05:10; round 1 is correctly re-presented at 04:23.
- No proof of what phones heard or whether their audio controls were absent: only the host screen is visible and the encoded track is silent.
- No assessment of cartoon metadata from this run: the cartoon source is not selected.
- No security clearance or public-release approval can be inferred from the video.

## Lessons for validation and delivery

The layout helper checks global overflow and minimum button sizes, but not usable name/answer width. A zero-width text column can pass. Scrolling fixtures often omit long automatic evidence; the end-to-end matcher test prepares complete synthetic metadata. These verify useful components but miss the mixed-quality library seen here. General Chromium tests allow gesture-free autoplay; an existing stricter test does not replace a complete first-start journey or physical devices.

The missing coverage is a realistic combined journey: five criteria, incomplete references, small desktop height, backward navigation, partial manual decisions, incomplete publication and native audio behaviour. FR/EN and zoom must be included. Assertions must verify that users can read and act, not merely that the document has no horizontal overflow.

Previous conclusions were broader than their evidence. The existence of features and successful suites should not have been presented as full validation of the desktop finale, accessible audio recovery or conviviality.

Repair order: **(1)** readable layout, resilient scrolling, live reference readiness and initial audio; **(2)** coherent setup, guided single input, compact finale, clear private/public actions and criterion-level progress; **(3)** truthful ceremony, accessible post-game choices and meaningful shared staging. Each group requires an observed complete journey with adverse cases before claiming delivery quality or public readiness. Production has not been changed by this analysis.
