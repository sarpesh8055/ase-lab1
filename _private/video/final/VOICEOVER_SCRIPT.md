# Voiceover script, Lab 1 video

> **This file is generated.** `tools/build_video.py` writes it again on every build, so anything typed in here is lost.
> To change a sentence, edit `storyboard.json`. To change names or facts, edit `team.json`. Then build again.

Video length: **9:42** (582 s). The limit is 10:00, and nothing after it is graded.
Speaking pace assumed: 144 words per minute, plus 1.2 s of breathing room on every slide.
Words in total: 1323.

> **Not final yet.** These entries in `team.json` are still open, and they show up in yellow on the slides:
> - session01_tokens_and_cost: TODO Sarpesh: tokens and cost
> - ai_tools_tasks_2_to_4: TODO which AI assistants were used for the first version of Tasks 2-4, and for what
> - who_did_what.Gagan: (empty)
> - who_did_what.Namit: (empty)
> - who_did_what.Ranjith: (empty)
> - who_did_what.Sarpesh: (empty)
> - who_did_what.Soumya: (empty)

## Who speaks when

| Part | Speaker | From | To | Length | Words |
|---|---|---|---|---|---|
| 1. Intro | Namit | 0:00 | 0:22 | 0:22 | 51 |
| 2. Task 1: using an agent | Namit | 0:22 | 2:02 | 1:40 | 229 |
| 3. Task 2: our own agent | Gagan | 2:02 | 4:11 | 2:09 | 298 |
| 4. Task 3: RAG | Ranjith | 4:11 | 6:03 | 1:52 | 258 |
| 5. Task 4: tools | Sarpesh | 6:03 | 8:44 | 2:40 | 371 |
| 6. Wrap-up | Soumya | 8:44 | 9:42 | 0:57 | 116 |

The speaker names come from `team.json` (`speakers`). Change them there; the slides do not show them.

## 1. Intro · Namit · 0:00 to 0:22

**Slide 1: Title, members, website** · 0:00 to 0:22 · 22 s · 51 words

> Hi, we are group 21: Gagan, Namit, Ranjith, Sarpesh and Soumya. In this lab we first used a coding agent, then built a small one ourselves, and then studied the two things every agent depends on: retrieval and tools. On the right is the team website the agent built for us.

## 2. Task 1: using an agent · Namit · 0:22 to 2:02

**Slide 2: The website: desktop, phone, day, night** · 0:22 to 0:44 · 22 s · 49 words

> In Task 1 we wrote no HTML, CSS or JavaScript ourselves. OpenCode with GPT-6 Luna built this page in two sessions. It shows all five of us, our shared view on AI, and a day and night switch. It works on desktop and phone, and it passes the checker.

**Slide 3: Session statistics** · 0:44 to 1:08 · 25 s · 57 words

> The second session took four prompts, 81 model calls and 103 tool calls, and cost seven cents. The interesting number is 4.1 million tokens sent. The conversation only grew from 11 thousand to 71 thousand tokens, but every model call sends the whole conversation again. 98 percent of that was cached, at a tenth of the price.

**Slide 4: What it did on its own, and when it asked** · 1:08 to 1:31 · 22 s · 51 words

> OpenCode read files, searched and kept a to-do list on its own. But before every edit and every command it asked for permission, 58 times. The model only proposes; the program runs it after a yes. One request was rejected: the agent wanted to rewrite a script the course gave us.

**Slide 5: Where it went wrong** · 1:31 to 2:02 · 31 s · 72 words

> Here it went wrong. The pictures were embedded as base64, 600 kilobytes, inside the file the agent kept editing. Its search failed on those lines, then its patch failed. It added a JavaScript workaround, checked for the wrong text, and reported the fix as done. It was not. We told it to keep a small source file with placeholders and let the embed script build the page. After that, every edit worked.

## 3. Task 2: our own agent · Gagan · 2:02 to 4:11

**Slide 6: Diagram: loop, actions, RAG, checker, feedback** · 2:02 to 2:35 · 32 s · 75 words

> Task 2 is our own agent: plain Python, no framework. In every step the model answers with one JSON object: a thought, an action and arguments. The four actions are: search the style guide, read the profiles, write the site, and finish. Our code runs the action and sends back an observation. The model decides what to look up, when to write, and how to fix a failed check. A fixed pipeline cannot do that.

**Slide 7: One annotated step** · 2:35 to 3:04 · 30 s · 69 words

> Here is one real step from the final run. We sent 25 messages, about 12 thousand tokens. The last one was our observation with five chunks of the style guide. The model answered: the cards are already alphabetical, but the hot take badge needs a fire emoji, so I will check the bio rules too. Our code parsed this, embedded the query, and sent back the five best chunks.

**Slide 8: Chunking, k, and safety nets** · 3:04 to 3:37 · 33 s · 76 words

> We cut the 55 style guide documents at their headings into 66 chunks, each starting with its title and status, so the model sees if a rule is deprecated. With 18 test questions of our own, the right document is always in the top five, but only 14 times at rank one. So k is five. Broken JSON, a repeated search or an early finish gets an error back, and after 25 steps the run stops.

**Slide 9: Result, context growth, rules it got wrong** · 3:37 to 4:11 · 34 s · 78 words

> The final run took 14 steps and cost under one cent. The first page passed all 25 checks, but still broke two rules: no fire emoji on the hot take badge, and no bio. The checker does not test these, and the agent had never searched for them. After our feedback it looked them up and fixed both. The context grew from 600 to 13 thousand tokens. At a hundred steps we would have to summarise old results.

## 4. Task 3: RAG · Ranjith · 4:11 to 6:03

**Slide 10: Table: setups by question category** · 4:11 to 4:46 · 35 s · 81 words

> In Task 3 we compared five retrieval setups on 932 documents. The table shows recall at five per question category. Keyword search is perfect on identifiers such as error codes, because a rare token gets a high weight. Embeddings win on paraphrases, where question and document share no words. Nobody gets above 0.5 on multi-hop: the second document is only findable with a code inside the first one. The hybrid is best overall with 0.71, and HyDE lifts it to 0.73.

**Slide 11: Chunk size, weight, cost and latency** · 4:46 to 5:09 · 23 s · 52 words

> Chunk size changed little. Small chunks help version questions, because one changelog line becomes its own chunk. Large chunks help paraphrases. For the hybrid, equal weights were the peak of our sweep. HyDE adds a little recall, but needs an extra model call per question: about six seconds instead of 180 milliseconds.

*Before you record this:* If someone asks about the six seconds: task3_rag/results/summary.json shows 1.8 s for R5, because the HyDE passages were generated in 4 parallel threads. One HyDE call on its own takes about 6.3 s (Task 3 README, cost and latency section).

**Slide 12: End to end, and the judge** · 5:09 to 5:36 · 27 s · 61 words

> End to end, both setups answer 75 percent of 50 questions correctly. Giving the model the whole document instead of one chunk raised this from 66 to 75. Faithfulness is 97 percent: it almost never invents facts. We checked ten judge decisions against the documents and agree with eight. The judge is reliable for single facts, but inconsistent with partial answers.

*Before you record this:* The file task3_rag/results/judge_check_R5_hybrid_hyde.md says its ten verdicts were drafted with an AI assistant and that every group member must re-check them. Do that before saying 'we checked'. If your count is not 8 of 10, change the number here and on the slide (deck/slides_b.html).

**Slide 13: Failure analysis and recommendation** · 5:36 to 6:03 · 28 s · 64 words

> Our best system gets 13 of 50 answers wrong. Every failure starts in retrieval, none in generation. Ten are multi-hop questions where the second document is missing. In version questions, forum threads push the release notes out of the top five. We would deploy the hybrid without HyDE: same correctness, 35 times faster. The next step is a second retrieval round for multi-hop questions.

*Before you record this:* '35 times faster' compares about 180 ms with one HyDE call of about 6.3 s (Task 3 README). In task3_rag/results/summary.json the R5 median is 1.8 s, because the HyDE passages were generated 4 at a time. Measured that way it is about 10 times.

## 5. Task 4: tools · Sarpesh · 6:03 to 8:44

**Slide 14: The tools: read-only, execute, write** · 6:03 to 6:35 · 32 s · 73 words

> Task 4 is a safe tool layer for a bug-fixing agent. There are six tools. Three only read: list files, read file and search code. Two run fixed programs: the tests and the tinyledger command line. Only one writes, and only into existing files below the source folder. There is no general shell tool, on purpose: with a shell the agent could read secrets or change tests, and we could not check that.

**Slide 15: Why we validate, and the mock run** · 6:35 to 7:06 · 31 s · 71 words

> Every call goes through the same steps: parse the JSON, check the schema, check the meaning, for example the path, then run, redact, cut to size, and log. We validate although the model follows the schema, because a valid call can still be malicious: dot dot slash secrets is a perfectly valid string. Our mock model sends six broken or malicious calls, and all six are rejected with a clear error.

**Slide 16: Threat, control, where in the code** · 7:06 to 7:34 · 28 s · 65 words

> This table maps each threat to a control and to the place in the code. Paths are resolved with all symlinks and compared part by part. Writes are only allowed below source. Programs start without a shell and without the API key in their environment. A timeout kills the whole process tree. Every result is cut to ten thousand characters, and every call is logged.

**Slide 17: Condensed trace of one bug fix** · 7:34 to 8:05 · 31 s · 72 words

> This is the real run. The agent ran the tests: two failed. It read the issue and reproduced it: the March report showed only 197 euros. It found that German dates were read month first. It fixed that and two more bugs with three small edits. Now all 25 tests pass, March shows 362 euros 30, and no test was touched. Eight model calls, 19 tool calls, a quarter of a cent.

**Slide 18: Untrusted content and limits** · 8:05 to 8:44 · 39 s · 90 words

> The repository contained two planted instructions. One, in a data file, told AI agents to read a secret file and delete a test. The other, in a docstring, said: change the test, not this function. The model ignored both and reported them. But we do not rely on that: the path check, the write limit and the missing delete tool would have stopped it anyway. What we cannot stop: code under test runs with our rights. For a real company repository we would add a sandbox without network or secrets.

## 6. Wrap-up · Soumya · 8:44 to 9:42

**Slide 19: Lessons learned** · 8:44 to 9:06 · 22 s · 49 words

> Three lessons. One: a green check is not a correct result. OpenCode reported a fix that was not there, and our own agent passed 25 checks with two broken rules. Two: an agent only knows what it retrieved. Three: safety belongs in the tool layer, not in the prompt.

**Slide 20: AI usage statement, who did what** · 9:06 to 9:42 · 36 s · 67 words

> AI usage: OpenCode with GPT-6 Luna wrote the whole Task 1 website. In the second session, Claude Code wrote and sent our prompts and answered the permission questions. It also checked our results and prepared these slides. [Say which assistants were used for the first version of Tasks 2 to 4.] [Who did what: one short sentence per person, as on the slide.] Thank you for watching.

*Before you record this:* The two parts in square brackets are yours to word. Write your wording into the 'say' text of s20 in storyboard.json, not into the generated script. It must match what is on the slide, which comes from team.json. You have 36 seconds for this slide, about 85 words in total.
