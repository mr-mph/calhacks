# Cal Hacks 13.0: tracks, rules and resources

Everything we found about prizes and logistics, including tracks we aren't entering, so nobody has to dig through
Slack again. Gathered Saturday Oct 24 from the Hacker Guide, Devpost, the Hive prizes page, sponsor emails and the
sponsor Slack channels. Prizes are "subject to change", so check the sponsor's Slack channel before relying on a detail.
Our choices and the reasoning: `CONTEXT.md` section 5 and `docs/pitch.md`.

## Rules and deadlines

| What | When / rule |
|---|---|
| Devpost submission | **9:00 AM Sunday**, hard deadline. Submit a draft Saturday night and keep editing |
| Table assignment | Shortly after 9 AM; be at the table by 10:30 AM |
| Judging | 10:30 AM to 12:30 PM Sunday. **Every teammate must be at the table** or the team isn't judged |
| Pitch | **3 minutes to pitch, 2 minutes of judge questions**, with a **live demo**. Devpost also asks for a clear demo video (sponsors judge async) |
| Submission must include | An **image of the project** and the **GitHub repo**; code without a repo isn't considered |
| Closing ceremony | 2:00 to 4:00 PM Sunday; winners' photos 4 to 5 PM |
| Team size | 1 to 4. Add teammates on Devpost; nothing else needed |
| Originality | All work must be started at the event |
| Venue rules | No personal hotspots or routers inside (they detect them), no soldering, don't unplug APs |
| Sponsor tracks | Tick each one on Devpost at submission. We found no cap on how many |

Devpost judging criteria (Cal Hacks prizes): **Application** (who it helps, would they use it), **Intentionality**
(every design choice has a reason), **Functionality** (live demo works, plus a clear video), **Creativity**,
**Technical Complexity**.

## Cal Hacks prizes (automatic)

| Prize | Award |
|---|---|
| First Overall | $3,600 cash + MacBook Air or Framework laptop each |
| Second Overall | Nintendo Switch 2 each |
| Third Overall | Google Intelligent Eyewear each |
| Most Technically Complex | NuPhy Air60 HE each |
| Most Creative | Instax camera + film each |
| Best Hardware Hack | Bambu Lab A1 Mini each |
| Best People-First Social Impact | Apple Watch SE 3 each |
| Best Planet-First Social Impact | America the Beautiful Parks Pass each |
| Best Beginner Hack | AirPods 4 each |
| Best Solo Hack | AirPods Pro 3 |
| Hacker's Choice | Logitech MX Master 4 each |
| SkyDeck | One startup-minded winner invited to SkyDeck's incubator (mentioned in the guide) |

## Sponsor tracks

"Us" marks what we decided. Fit notes are for a tethered camera balloon.

### Entering

**Anthropic: Claude for Public Benefit** (co-host). Us: in.
- Prize: $5,000 in Claude credits, 1 year of Claude Max 20x, office hours with the Anthropic team.
- Judging: (1) a *named community*: "students" is too broad, "transfer students at Berkeley trying to find housing"
  is the right size; (2) a real problem you lived or heard from someone who did; (3) it works, and one thing usable
  on Monday beats a broad demo; (4) Claude does something that matters, and you know where it could go wrong.
- Slack: `#cohost-anthropic`. Claude Corner coffee chats at the booth.
- Saturday 7:49 PM, Anthropic judge: no single main criterion; all four count equally. They want a thoughtfully
  designed product built and running meaningfully on Claude that solves a specific community's problem in a way
  that's **tangible and measurable**, and "the narrower, the better". For us: Ocean Beach swimmers and patrol, and
  numbers we can show (alerts drafted, time from frame to confirmed alert, people counted near a rip).
- Full Anthropic post (Friday, `#cohost-anthropic`): they want "a fully working product, not a concept", and it should
  be **clear how you plan to measure its impact** on the community. Prize also includes an invite to visit Anthropic HQ.
  Our measure: the Alerts page stats strip (alerts drafted, seconds from frame to confirmed alert, people near rips).
- Saturday 8:18 PM: optional 2-minute "Claude Student Survey" form in `#cohost-anthropic`; about 20 random submitters get
  a printed copy of Anthropic safety research.

**Hyphenate: The Hyphenated Enterprise, Autonomous Systems for Finance** (co-host). Us: in.
- Prize: $8,000 / $5,000 / $3,000, plus an expedited interview for the top 5 teams.
- Four judging questions: Is it real enough (realistic data, a messy problem, proof it works)? Would you hire it, and
  for which roles (limited access, a clean record of its work, knowing when to ask)? Did we see something new? The
  moment: when it catches what others missed, recovers from a failure, or defends a decision when questioned.
- Bring: a demo video that opens with that moment, a live demo (they may try their own scenario), one line on the
  roles it fills, and what's real vs. simulated.
- Slack: `#cohost-hyphenate` (workshop recording and slides pinned). Select the track on Devpost.
- Saturday 5:50 PM, Hyphenate team: bring your early MVP or raw idea to their booth and talk it through with them
  before submitting (they're running office hours there).

**Spacetime: Best Use of Spacetime** (co-host). Us: in, for the prediction market.
- Prize: $2,048 / $1,024 / $512.
- Wants Spacetime as the core real-time backend: live shared state, multiplayer, instant sync. Their own examples
  include prediction markets, auctions, trading sims and live dashboards. "Meaningfully used, not added on the side."
- Separate contest, no Devpost needed: **Scrabblebot tournament** (bots bid on Scrabble letters), $1,024 / $512 / $256,
  at scrabblebot.spacetimedb.com.
- Slack: `#cohost-spacetime`.

**Convex: Best Use of Convex.** Us: in if time.
- Prize: $5,000 cash to one team.
- Reactive TypeScript backend: write to the database and every connected client updates live.
- Hardware note: an alpha Convex client for the ESP32 exists (github.com/convex/convex-esp32).
- Start at convex.dev (copy the prompt into your coding agent); resources at convex.dev/hackathons/resources.
  Workshop Saturday 4 PM. Slack: `#spons-convex`.

**SpaceXAI: Make it Legendary.** Us: in.
- Prize: a custom Cursor mechanical keyboard per member (Devpost also lists $400). Everyone who submits enters a raffle
  for a Cursor water bottle.
- Brief: real space data in, a legendary project out. **Must be built with Cursor** ("the more you use Cursor, the
  more likely you win"). The Hacker Guide also requires the Grok Imagine or Voice API; the Slack post lists Grok Bot
  only as a bonus. Ask at their booth.
- A 1-month Cursor/Grok premium QR code was handed out at their workshop; ask in `#spons-spacexai` if you missed it.

### Maybe

**Atlassian: Agentic Workforce Challenge.**
- Prize: AirPods Max + swag.
- Build a Forge app for Jira or Confluence. Track 1: agents that do team work (issue triage, keeping docs current).
  Track 2: security for agents (prompt-injection defense, audit and rollback).
- Judged on creativity, usefulness to Atlassian users, and technical use of Forge. A 3-minute demo video and a repo
  link are required on Devpost.
- Setup (~15 min): Node 22 or 24, `npm i -g @forge/cli`, API token with Forge scopes, `forge login`,
  `forge site provision`, `forge register`, `forge deploy`, `forge install --demo-site --product jira`.
  Starter code: github.com/atlassian-labs/forge-inspired. Slack: `#spons-atlassian`.
- Our idea: balloon alerts become Jira incidents routed to whoever is on patrol; each day becomes a Confluence report.

**Microsoft: Built for the Real World** (grand prize) and **Customer Impact Award**.
- Grand prize: a Surface laptop each, a remote talk at a Microsoft FDE team tech talk, 1:1 mentorship. The Customer
  Impact Award gets the talk and mentorship.
- Build a production-minded AI agent for finance, productivity, healthcare or another high-impact area. Judged on
  customer understanding, measurable usefulness, path from prototype to production, responsible design, and
  end-to-end function. Azure for Students credits are available. Slack: `#spons-microsoft`.
- Our idea: the same agent as Hyphenate, pitched for this audience.

### Not entering (for reference)

| Track | Prize | In short |
|---|---|---|
| Visa: Reimagining Shopping | $5,000 | Innovation 25%, UX 25%, tech 20%, commerce impact 15%, trust 15% |
| Mana | $5,000 | Build with Mana and link the Mana pages or chats you used; all teams get 3 months of Mana Pro |
| Creao AI (3 tracks: AI-First Disruptor, One-Person Company, Team Empowerment) | $3,000 cash + Creao Pro Max year each | Build on Creao |
| Apify | $2,000 / $1,000 / $800 / $400 / $400, plus Best Actor $400 | Meaningful use of Apify scrapers ("Actors") |
| Factory: Droid SDK | $2,000 + credits | Droid must do real work in the running product, on a trigger you designed, with visible steps |
| Coinbase: x402 (two tracks) | $500 USDC + recruiter call per member, per track | Agentic payments with x402 and the Coinbase MCP. Possible fit: sell balloon counts per request |
| Fetch.ai | $1,500 / $1,000 / $500 | Agents on Fetch.ai (details at fetch.ai/events/calhacks-13-0) |
| Bright Data | Credits + Amazon cards, top 3 | Live public web data must be essential; no mocked data |
| CRS Credit API | $1,000 overall, $500 financial agent, interviews | Live use of the CRS credit sandbox |
| Cartesia | Meta glasses (TBD) | Voice must be core. Judged 25% each on problem, Cartesia use, execution, responsibility |
| Moss | AirPods Max/Pro | Voice AI, personal agents, or social posts with Moss retrieval |
| Figma (5 prizes) | $1,000 Amazon card each + recruiter session | Best Design, Most Creative, Figma Agent uses |
| Elastic | Meta Quest 3S / Bose QC | Elastic Agent Builder on Serverless |
| Bitdeer AI Model Studio | $500 / $200 credits + mice / LEGO | Build on Bitdeer's model API |
| Meta: Bringing People Closer Together | Invite to Round 2 at Menlo Park | Strengthens human connection with AI |
| Capital One: Nessie | $300 gift card each | Capital One's mock banking API |
| Armadin: Best Security Hack | Apple headphones | Details "coming soon" |
| Notability | 1 yr Pro + merch | Your build notes in Notability |
| MLH: Gemini, Solana, Tiger Data, Vultr, Snowflake, GoDaddy domain | Swag-level prizes | Tiger Data (Postgres for time series) explicitly mentions real-time IoT monitoring |
| MLH: Commit Fellowship | Interview for a 3-week founder sprint | Working prototype + a supplemental form after submitting |

## Devpost prize list changes (Saturday 9 PM)

- **Atlassian** is now "Best Agent / Best Security Solution for Agents", 4 winners (AirPods Max each). **Say which track
  in the project description.** We enter Best Agent (Balloon Patrol triages and files incidents) and mention the
  security layer (audit, revert, injection defense).
- **SpaceXSI** on Devpost: must be built with Cursor; Grok Bot for planning is a bonus (no Grok API requirement listed).
  Submitters enter a raffle for a Cursor water bottle; winners get a Cursor keyboard each.
- **Convex:** "Use real Convex features like live queries and components to win."
- **Anthropic: Claude for Public Benefit** is now on Devpost ($4,998 listed, plus Claude credits, Max 20x, office hours).
- **Hyphenate:** 5 winners ($8k / $5k / $3k cash, expedited interviews for the top 5).
- **CRS:** now $2,000 / $1,000.

## Free credits and resources

| Resource | How to get it |
|---|---|
| Claude credits | Redeemed through the event (check `#cohost-anthropic` if they landed in a team org instead of personal) |
| RunPod GPU credits | QR code pinned in `#spons-runpod`, or their booth |
| Bitdeer credits ($50) | Form from their workshop; credits can take a while to show up (`#spons-bitdeer`) |
| Azure for Students | Linked in `#spons-microsoft` |
| Cursor + Grok 1 month premium | QR code from the SpaceXAI workshop (`#spons-spacexai`) |
| Mana Pro (3 months) | Every team that uses Mana |
| Spacetime maincloud credits | Redeem link with a Cal Hacks code, posted Saturday 12:10 AM in `#cohost-spacetime` |

## Hardware at the venue

- **Hardware desk (Mezzanine):** Arduino Uno kits, Raspberry Pis and Picos (with HDMI cable and microSD card),
  ESP32s, MPU6050s, common sensor modules, Ethernet patch cables. Opens after Friday's opening ceremony; everything
  is due back by 2 PM Sunday.
- **3D printing:** five printers with PLA; sign up through the form, 3.5 hours max per print.
- **No soldering** inside the venue.

## Workshops and people (Saturday)

- Anthropic: Building Multi-Agent Teams, 1 to 2 PM, Theater.
- Bitdeer: 1 to 2 PM, Gate 4, Breakout 4.
- Annapurna Labs (AWS chips): technical talk 3 to 4 PM in the Theater, then networking 4 to 6 PM at Gate 6.
- Convex: building agentic apps, 4 PM.
- Questions for organizers: `#0-ask-directors`. Mentors: `#1-ask-mentors` or the mentor tables. Hardware: `#1-hardware`.
