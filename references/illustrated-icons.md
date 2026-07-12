# Illustrated Icon Art Direction — "Neon Sketch Duotone"

Archscribe's illustrated icons are original procedural SVG objects. They do not copy external artwork and do not require network assets.

## Design language

- **Plate-free duotone.** No base disc, no gradient badge. Structure strokes use the theme ink (`white` in dark themes, near-black in light themes) with a hand-drawn ghost pass offset behind them; exactly one semantic accent color paints the moving part. On dark themes a faint accent glow disc breathes behind the icon.
- **One job story per icon.** Every icon performs a single physical action per cycle — a signal travels, a chip drops, a shackle clicks — with anticipation, overshoot, and settle. `update(p)` is deterministic in `p ∈ [0,1)`; `p=0` equals `p→1`, so GIF loops are seamless.
- **Golden-ratio stagger.** Icons on one canvas are phase-offset by `0.618·index`, so a static PNG shows varied mid-story poses and an animation never moves in lockstep.
- **Fixed hand tilt.** Each family carries a constant ±1.4° tilt (no per-frame jitter), preserving the Excalidraw feel without shimmering.

## Job stories (builder → what happens each cycle)

| Builder | Keys (prefix match) | Story |
| --- | --- | --- |
| brain | brain, think, model, reason | synapse signal crosses two circuit arcs, nodes flash, lobes breathe |
| agent | agent | robot blinks, glances aside, antenna pings a ring |
| gear | gear, act, tool*, settings, etl, load-balancer | drive gear turns one pitch with backlash, pinion counter-rotates, mesh sparks |
| eye | eye, observe, monitor | iris glances left/right, cartoon blink closes the loop |
| db | db, database, memory, working-memory, warehouse, lake, storage | record chip drops into the cylinder, lid bounces, shelves shimmer |
| search | search, scan | magnifier sways, accent scanline sweeps, hits flash |
| shield | shield, validate, guard*, check, admin, warning, compliance | threat particle blocked at the rim, then the check draws on |
| clock | clock, budget, schedule, pending, time | minute hand ticks a full revolution with arc trails |
| message | message, chat | typing dots bounce, bubble squashes, broadcast rings |
| api | api | request token flies through the brackets, response returns |
| package | package, output, deliver, cube, box | flaps swing open, delivery arrow pops out, box closes |
| cloud | cloud, deploy | upload dashes stream into a bobbing cloud, rim flashes |
| server | server | rack LEDs blink in order, data line hums |
| cluster | cluster, kubernetes | heartbeat pulse travels the three-hex mesh |
| container | container | cargo crate hops inside the hex hull, lands with a squash |
| queue | queue | chips advance one conveyor slot; one exits, one joins |
| cache | cache | lightning strikes the stack, the hot layer flashes |
| vector | vector-db | constellation glint hops the edges, nodes swell in turn |
| embedding | embedding | scattered tokens funnel down into an ordered vector row |
| stream | stream | payload dots ride the wave path |
| rag | rag | scan bar reads the open book, grounded lines light up |
| prompt | prompt | input pill types a line, the send key fires a ring |
| terminal | terminal, code | command types after the chevron, response line answers |
| lock | lock, secret, key | shackle pops open, drops shut, keyhole pings |
| identity | identity | badge shine sweeps the ID card, avatar checks in |
| user | user, customer, team, human | a nod hello, then the presence dot pings |
| audit | audit, clipboard, manual-step, evaluation | checks stamp down the clipboard line by line |
| file | file, document, policy | lines write themselves onto the page |
| folder | folder | folder opens a crack, a document peeks out |
| notification | notification | bell swings with decaying ring waves |
| analytics | analytics, dashboard | bars surge in sequence, trendline draws across |
| globe | globe, world, cdn | meridians roll by, a point of presence pings |
| success | success, approve | check stamps in with a bounce and a halo |
| failure | failure | cross slams in, the badge flinches |
| retry | retry | loop arrow whips one full revolution |
| trigger | trigger, event | bolt strikes, shockwaves radiate |
| scope | scope | target drifts, the reticle locks on |
| firewall | firewall | threat dart deflects off the bricks, impact ring |
| module | anything else | IC chip core pulses, pins glint in sequence |

### Loop workflow pack (control flow, delegation, evaluation, recovery)

| Builder | Keys (prefix match) | Story |
| --- | --- | --- |
| loop | loop, iterate, cycle | twin chase arrows swing half a turn and hand off |
| plan | plan, roadmap | the route draws across the folded map, waypoints light up |
| decision | decision, condition | a token enters the diamond, it deliberates, routes onward |
| merge | merge, join, aggregate | two lane payloads fuse into one heavier token |
| split | split, fanout, parallel, branch | one payload fans out into two parallel branches |
| handoff | handoff, delegate | the baton arcs from one runner node to the next |
| subagent | subagent, worker | the parent boots a mini worker at its side |
| orchestrator | orchestr*, coordinator, dispatch | the conductor dispatches to three workers in turn |
| human | human, review, approval, hitl | the reviewer holds the gate, nods, then approves |
| checkpoint | checkpoint, milestone | a runner dot reaches the planted flag, which flaps |
| rollback | rollback, revert, undo | a glint rides the rewind arc back to the earlier state |
| sandbox | sandbox, experiment, lab | the experiment bubbles inside the flask |
| compare | compare, ab-test, benchmark, versus | A/B panels trade weight on the balance |
| score | score, grade, rating, rank | the meter fills and the star stamps its rating |
| error | error, exception, fault, warning | the warning triangle flinches and the bang blinks |
| wait | wait, delay, timeout, sleep | the hourglass drains, then the sand fades back full |
| emit | emit, broadcast, publish, webhook | the beacon mast broadcasts expanding waves |
| ingest | ingest, intake, import, receive | payloads drop into the intake tray, which absorbs each hit |

The loop pack QA sample is `assets/examples/loop-icon-pack-spec.json` (20 distinct workflow semantics across control flow, delegation, evaluation, and recovery).

## Motion contract

- `icon_motion: "auto"` (default) plays the builder's intrinsic job story. Legacy preset names (`think-pulse`, `gear-spin`, …) are still accepted and treated as `auto` — the story is bound to the semantic key, not the motion field.
- `icon_motion: "none"` freezes the icon at its rest pose (`p=0`).
- Story pacing targets ~2.4 s per cycle; longer narrative presets (`draw`, `relay`, `chapter`…) run an integral number of cycles so the loop stays seamless.
- In the `draw` preset, illustrated icons fade in as complete objects (their internal dash animations are excluded from the whiteboard stroke reveal).

## Color contract

- `ink` = theme glyph color (`op.glyph`), `ghost` = ink at ~30 % alpha, offset (0.75, −0.55).
- `accent` = the item's spec color (`op.accent`); soft fill at 20 %, mid at 55 %.
- Threat particles (shield, firewall) use the theme's `pink`.
- Light themes reduce ghost alpha and glow strength (~55 %).

Use no more than three hero icons in one visual region. Secondary cards should use `illustrated` or `outline` so the hierarchy remains clear.

## Silhouette discipline

Do not reuse one badge for unrelated concepts. Near-neighbor concepts must still differ: Agent is a robot face rather than a brain; Identity is an ID card rather than a padlock; Stream is a wave path rather than a queue conveyor; Prompt is an input pill rather than message dots; Cache is a struck stack rather than a database cylinder.

The visual QA sample is `assets/examples/illustrated-icon-catalog-spec.json`, which renders 25 semantic illustrations across AI, data, infrastructure, security, and experience families.
