# Sparse-vocal melodic techno / house

Added 2026-09-27 as the third musical theme in Night Drive, alongside synthwave
and Russian hip-hop. There are five selectable profiles: three synthwave variants,
one Russian vocal profile and this house profile. Uniform random selection gives
each individual profile an expected 20% share of songs, not a fixed schedule.

Current version: harder, groove-led melodic techno/house with sparse Russian
female vocals and extended instrumental sections. The original melodic-house
research is retained below; the Anyma-inspired revision at the end supersedes
its vocal-led arrangement. Exact BPM and key remain model-selected.

## Original research and interpretation

- [Rae Morris live review, The Independent](https://www.the-independent.com/arts-entertainment/music/reviews/rae-morris-live-heaven-london-someone-out-there-a8279571.html)
  highlights elastic, expressive singing. [David Smyth's Evening Standard interview](https://davidsmyth.co.uk/2018/02/rae-morris-interview-evening-standard-2-feb-2018/)
  describes a high, sweet voice in an electronic-pop setting.
  Our translation is a luminous upper register, agile phrasing, and a contrast
  between intimate verses and an emotionally open hook. This describes a broad
  performance approach, not a claim to reproduce her voice.
- [Lane 8's interview with Salacious Sound](https://salacioussound.com/2015/06/interview-lane-8/)
  places emotional melody, harmony and chord changes at the center of his writing;
  he also discusses instrumental music strong enough to stand without a vocal
  and recorded shaker textures. He explicitly resists a generic deep-house label.
  We use melodic progressive house, with the voice and an instrumental motif
  sharing attention. Rolling bass, evolving synth textures, a steady house groove,
  gradual development and bittersweet warmth are our arrangement choices.

The caption contains musical traits, not artist names or reference audio.
Exact BPM and key remain unset, continuing the station's looser prompting.
A four-on-the-floor groove is the rhythmic house cue; no exact melody or chord
progression is prescribed. The 210-second duration leaves room for an instrumental
break, while preserving complete-song generation and bounded storage.

Lyrics are original Russian text, titled “Между огнями” (“Between the Lights”):
leaving a crowded room, walking through the city at dawn, and allowing yourself
to change. Short lyric lines and an instrumental break leave room for the groove.
`vocal_language: ru` and a Russian-vocal caption cue guide pronunciation. This is
new content, not a translation of the earlier English audition. The profile's
words remain fixed between renders; no lyric-library feature is implemented.

A listening review is required to judge resemblance of mood, vocal quality and
musical appeal; a successful duration/decode test alone does not establish them.

## Original English trial on this host

RTX 3060, XL/4B: 210 seconds of audio generated and normalized in 127.70
seconds, plus 69.27 seconds of model initialization. Ratio to usable playout:
0.623 (passes the 0.8 threshold). Model-selected metadata was 125 BPM / E major.
Preview is on the existing local/LAN audition page as “Let the Morning Find Us”.

## Russian revision (2026-09-27)

Replaced the English lyric with new original Russian lyrics at Taylor's request.
The female-vocal house character, 210-second duration, automatic tempo/key and
20% expected selection share remain. The English audition is retained separately.

## Groove-led melodic techno revision

Taylor requested a harder Anyma-inspired direction and less dominant vocals.
[Anyma's Billboard Italia interview](https://billboard.it/interviste/anyma-intervista/2026/09/04209352/)
describes cinematic, introspective melodic techno rooted in club records and an
initial focus on sound design. Our translation emphasizes a punchy kick, rolling
sub bass, sharp syncopated synth stabs, dark evolving arpeggios, and instrumental
drops. These are prompting choices, not a claim to copy a particular recording.
The upper-register female vocal character remains, but as brief Russian accents.

The lyric was reduced to eight sung lines across three short vocal appearances,
with instrumental intro, builds, drops, break and outro. This changes both caption
and structure so the groove has more room. Instrumental section markers guide
the model; they do not guarantee an exact vocal/instrumental time ratio. Tempo/key
remain automatic. The softer Russian trial was superseded before deployment.

Russian groove-led trial: 210 seconds generated and normalized in 124.94 seconds
(0.609 of usable playout), plus 62.15 seconds of model initialization. Preview:
`http://localhost:8082/06-mezhdu-ognyami.mp3`. Listening review pending.
