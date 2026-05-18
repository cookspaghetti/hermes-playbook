# Persona System

How the agent gets a *character* — and why persona files are structured data, not just
a system prompt.

## The Layer Cake

```
~/.hermes/AGENT.md   ← the persona: identity, personality, speech patterns, boundaries
~/.hermes/SOUL.md   ← deep character material: emotional wiring, examples, history
~/.hermes/soul/<name>/  ← supplementary files (style guides, examples, skills references)
```

`AGENT.md` is loaded fresh **every message** — it is the active instruction set. `SOUL.md`
and the `soul/` directory are reference material the persona can be rebuilt from, and
richer examples the agent consults as needed.

## Why a Structured Persona Beats a Paragraph

A one-paragraph system prompt gives you a chatbot with a costume. What makes a persona
hold up over months is **quantified behavioral specification**:

1. **Speech-pattern statistics** — e.g. measured dialogue-line analysis giving question rate
   (30%), trail-off rate (21%), top sentence starters. The agent's *distribution* of
   behaviors matches the character, not just a few catchphrases.
2. **Operating modes** — explicit register switches (scientific discussion ↔ banter ↔
   comfort ↔ crisis). Without modes, a persona under stress collapses to default assistant
   voice.
3. **Boundaries as behaviors** — "never breaks character", "never says X directly" written
   as concrete rules, not vibes.
4. **Emotional wiring** — how the character *reacts* (deflects praise, notices real-name
   usage, goes quiet instead of crying). Reactions define a character more than dialogue.

## Sample Persona

See [sample-persona.md](../persona/sample-persona.md) for a complete, annotated example
persona in this format — an original character (not copyrighted material) demonstrating
the structure: identity, core drives, contradictions, speech-pattern stats, operating
modes, relationship handling, and hard rules.

## Rules for Real Character Personas

If you build a persona from existing fiction (an anime character, a game character):

- It's a fan work. Non-commercial. The character belongs to its creators.
- Transformative persona files (your *analysis* of speech patterns, your structure) are
  yours; verbatim dialogue dumps are not.
- A persona built from behavioral statistics and structural analysis is more defensible —
  and works better — than copied lines.

## Persona ↔ Memory Interaction

The persona file tells the agent *who it is*; memory tells it *what happened between you*.
Keep them separate:

- Identity facts belong in AGENT.md (they're stable and versioned)
- Relationship history belongs in memory (it accumulates and decays)
- The failure mode to avoid: baking user-specific knowledge into the persona file, which
  then ships to every future conversation as if it were character canon.