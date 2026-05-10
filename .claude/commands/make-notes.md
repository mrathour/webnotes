Read a captured text file and convert it into a structured markdown note.

`$ARGUMENTS` contains three space-separated values:
```
<stem> <saved_dir> <notes_dir>
```
- `stem` — filename without extension (e.g. `capture_20260509_150342`)
- `saved_dir` — absolute path to the folder containing `.txt` captures
- `notes_dir` — absolute path to the folder where `.md` notes are written

Source file: `<saved_dir>/<stem>.txt`
Output file: `<notes_dir>/<stem>.md`

## Steps

1. Parse `$ARGUMENTS` to extract `stem`, `saved_dir`, and `notes_dir`.

2. Read `<saved_dir>/<stem>.txt`. It has this structure:
   ```
   URL:       <url>
   Title:     <title>
   Tag:       <tag>
   Captured:  <timestamp>
   ============================================================

   <raw captured text>
   ```

3. Parse out the metadata fields (URL, Title, Tag, Captured) and the raw text body below the separator.

4. Generate a structured markdown note from the raw text using these instructions:

You are an expert at converting raw input 
into revision-ready study notes.

GOAL
The notes will be used for long-term 
revision. They must be:
- Complete: no important concept missed
- Concise: no filler, no repetition
- Clear: instantly understandable 
  when read months later
- Self-contained: no prior context needed

STRUCTURE
- Break content into numbered sections
- Each section covers exactly one idea
- Order sections the way a reader 
  needs them: build understanding 
  progressively
- Use the most natural format per 
  section — prose, bullets, table, 
  or code block — whichever makes 
  the concept clearest fastest
- End with a brief summary that 
  captures the full picture in 
  2-3 sentences

CONTENT RULES
- Preserve every distinct concept, 
  term, rule, and example from 
  the source
- Fill gaps with accurate knowledge 
  where the source is vague or 
  incomplete — do not leave 
  incomplete explanations
- If something can be shown more 
  clearly with an example, add one
- Never pad, never repeat, never 
  explain what you are doing

OUTPUT
- Markdown only
- No preamble or commentary
- Just the notes

5. Create `<notes_dir>/` if it does not exist, then write the note to `<notes_dir>/<stem>.md`.

6. Report what was written: full output path and whether it was newly created or overwritten.
