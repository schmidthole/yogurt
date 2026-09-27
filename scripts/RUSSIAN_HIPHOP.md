# Russian melodic hip-hop profile

The fourth Night Drive profile adds a vocal song to the same station. Profiles
are selected uniformly at random, so its expected share is 20% of generated
songs; this is not a strict every-fifth-song schedule. Existing synthwave
profiles remain instrumental.

## Style research and production choices

MACAN's catalog varies, but the useful description for this request is
**minimalist, melancholic Russian melodic street rap** (often called
«пацанский рэп»): direct conversational verses, emotionally sung hooks with
sustained vowels, economical beats, and urban relationship/loyalty themes.

- [Afisha's musical analysis](https://daily.afisha.ru/music/26922-brat-my-za-tradicionnye-cennosti-kak-macan-stal-licom-molodoy-rossii/amp/)
  describes minimal rap beats, melodic hooks, and stretched chorus vowels.
- [T—J's overview](https://t-j.ru/macan-molodets-2025/)
  describes street-rap themes, melancholy relationship songs, and variation
  between minimal beats and other rhythmic approaches.
- [Meduza's contemporary review](https://amp.meduza.io/amp/feature/2023/01/16/glavnye-pop-zvezdy-2022-goda-anna-asti-macan-i-instasamka-edinstvennyy-vyvod-kotoryy-mozhno-sdelat-iz-ih-novyh-trekov-nichego-ne-proishodit-razvlekaemsya-dalshe)
  describes concise, minimalist hip-hop with trap beats and alternating rap
  and quiet singing.

The current caption keeps minimalist instrumentation, emotional male vocals,
conversational rap, a heartfelt melodic hook, and a nocturnal mood. Tempo, key,
meter, exact instruments, vocal register, and bar-by-bar arrangement are left
open so ACE-Step can choose a different musical setting per render.
The original trial used 140 BPM half-time, B minor, piano and 808 bass;
those were station production choices, not defining traits of every MACAN song.
The generation caption specifies musical traits without an artist name or
reference recording. The Russian lyrics are original, about returning home,
regret, and honest conversation; they do not quote an existing song.

## ACE-Step prompting

The [official guide](https://github.com/ace-step/ACE-Step-1.5/blob/main/docs/en/Tutorial.md)
separates overall sound in the caption from song structure and words in the
lyrics. Keep section labels short, write lyrics in Cyrillic, and explicitly
set `vocal_language: ru`. Lyrics stay below
ACE-Step's 4096-character limit. We disable language rewriting for explicit
languages, retain the XL/4B models and eight-step generation, and derive
instrumental mode from whether the profile supplies nonblank lyrics.

The configured lyrics are deliberately fixed: each render varies the melody,
arrangement, and performance, but repeats the same words. Fresh lyrics per
song would need a separate lyric-writing stage. Generating the whole 180-second
song preserves verses and hooks; short segment generation is not used.

## Local validation (2026-09-26)

On the RTX 3060 with XL/4B and INT8 DiT, the first 180-second vocal
render took 112.07 seconds including normalization (66.97 seconds separate
model initialization). The ratio to 175 seconds of usable playout is 0.64,
passing the existing 0.8 threshold. This is one timing sample, not a guarantee
for every render. Duration and stream decoding passed; pronunciation and
musical quality still require listening. Preview: `http://localhost:8082/`.

## Looser generation (2026-09-27)

Removed exact BPM/key overrides from all four profiles and shortened the captions.
The adapter enables metadata generation with unset tempo/key/meter, while preserving
an explicitly configured BPM or key when supplied. Random seeds were already enabled.
Duration stays fixed for queue accounting and storage bounds. The prior benchmark
above describes the original constrained profile; listen to new renders to assess
whether the wider musical choices improve variety. Lyrics remain fixed.
