# MealMate v2 — Requirements

| | |
|---|---|
| Status | Agreed baseline, 2026-09-26 (reviewed; owner decisions Q-1..Q-3 answered, see [§ 8](#8-owner-decisions)); last updated 2026-10-02 (UI rework, D-22..D-28) |
| Owner | Tobias Fischer (@Bublemann) |
| Companion document | [`plan.md`](plan.md): architecture, data model and milestones |

This document says **what** MealMate v2 must do. [`plan.md`](plan.md) says **how** and **in which order** it gets built.

**How to read it**
- Every requirement has a stable ID (e.g. `LIST-04`). Tests, pull requests and issues refer to these IDs.
- *Postponed* items are recorded in [§ 6](#6-postponed--future-ideas) so the design does not block them, but they are not built in v2.0.
- The decisions behind the less obvious rules are listed in [§ 7](#7-decision-log).

---

## 1. Purpose and scope

MealMate is a self-hosted web app for a small group of people (one household, 1–10 users) that turns **saved meals** into a **category-sorted shopping list** for fast supermarket trips. It keeps a shopping history per user.

**In scope for v2.0**
- Accounts with invite-only registration.
- Couples who share shopping lists.
- A shared ingredient database with nutrition data and barcode scanning via Open Food Facts.
- Meals with recipes, photo and source link.
- Shopping lists built from meals plus extra items, checked off in the store (also offline), with history.
- Export to the iOS share sheet (e.g. Notes).
- German and English UI.
- Operation on a Raspberry Pi 3, reachable from anywhere via Tailscale, with backups and alerts.

**Out of scope for v2.0:** see [§ 6](#6-postponed--future-ideas).

## 2. Users and usage context

- **Users:** 1–10 people, currently one household. Some are single; some form a *couple*.
- **Devices:** mainly iPhones (Safari, used as a Home Screen web app). Desktop browsers must also work.
- **Where it's used:**
  - at home, when planning meals and building lists;
  - in the supermarket, with poor, unreliable or no mobile signal, for checking items off.
- **Effort principle:** the least possible effort for users.
  - **One-time setup:** install the Tailscale app and accept the Pi share, tap one invite link and register, then "Add to Home Screen". The Home Screen app may need **one** login. It keeps storage separate from Safari; see ACC-07.
  - **Everyday use** must not require toggles, logins or manual syncing.

## 3. Glossary

The domain terms (ingredient, meal, shopping list, line, couple and the rest) are defined in [`CONTEXT.md`](../CONTEXT.md) at the repo root, the single glossary for docs, code and tickets.

## 4. Functional requirements

### 4.1 Accounts and sign-in (ACC)

- **ACC-01** Registration is only possible with a valid **invite**. There is no open sign-up.
- **ACC-02** Only admins create invites. An invite:
  - is single-use and valid for 7 days (configurable);
  - can be revoked;
  - always creates a normal *user* (an admin can promote the user later).
- **ACC-03** Creating and sharing an invite takes two taps:
  1. **"Create invite"** shows the link (`https://<app>/join#<code>`).
  2. **"Share"** opens the **native share sheet** (WhatsApp, Messages, Mail, …) with a prepared message in the admin's language.

  Where no share sheet exists, a copy button is offered. The prepared message has two steps: (1) accept the Tailscale share, (2) tap the link to register.
  - The invite form has an optional field for the **Tailscale share link**. The owner creates that link in the Tailscale admin console, and if it is filled in, the message includes it as step 1.
- **ACC-04** The code is in the URL **fragment** (`#…`), so it is never sent to the server by a link preview and never appears in server logs. It is consumed only when the registration form is **submitted**.
- **ACC-05** Registration asks for:
  - a **username**: used for login, 3–30 characters from `a–z 0–9 . _ -`, unique ignoring case;
  - a **display name**: shown to others, 1–40 characters, unique ignoring case;
  - a **password**.

  The UI language is preselected from the phone language. No email address is collected.
- **ACC-06** Password rules:
  - at least 8 characters and at most 72 bytes;
  - no forced symbols or digits;
  - rejected if it equals the username or is on a common-password list.

  iOS password autofill and strong-password suggestions must work (correct `autocomplete` attributes).
- **ACC-07** After registering or using a reset link, the user is logged in immediately **in the browser where the link was opened** (usually Safari). iOS keeps the Home Screen app's storage separate from Safari, so the Home Screen app may need one login. M1 checks on a real iPhone whether the login carries over. The join guide says "log in once if asked".
- **ACC-08** Users stay logged in as long as they use the app at least once every **90 days** (sliding expiry). This must survive closing the app and restarting the phone, which M1 verifies on an iPhone.
- **ACC-09** Users can:
  - see their active sessions;
  - log out the current device;
  - log out **all devices**;
  - change their password (which logs out all other devices).
- **ACC-10** Forgotten password: an admin creates a single-use **reset link** (`/reset#<code>`), valid 24 h, and shares it the same way as an invite.
  - Using it sets a new password and ends all of that user's sessions.
  - Afterwards the user sees "Password reset by *<admin>* on *<date>*" in *Me → Security*.
- **ACC-11** Wrong login attempts slow down further attempts for that username and client (increasing delay). No account is ever permanently locked.
- **ACC-12** The **first admin** is created with a command on the Pi (`mealmate create-admin`), interactively. A non-interactive form exists for automation and tests. If the last admin is locked out, `mealmate reset-link <username>` prints a reset link and also reactivates the account.
- **ACC-13** Users can change their display name, language and privacy settings.

### 4.2 Couples (CPL)

- **CPL-01** A user can send another user a **couple request**. The other user can accept or decline it, and the sender can cancel it.
  - The picker lists all active users by display name.
  - A user can be in at most one couple.
  - A user can have at most one outgoing pending request.
  - Accepting cancels all other pending requests that involve either user.
- **CPL-02** Each shopping list has a **"shared with partner"** switch. It defaults to **on** for new lists while the owner is in a couple, and only the owner can change it.
  - **On:** it is a *shared list*. The partner can edit it (CPL-03) and gets it in their local copy (SYNC-02). In both partners' Lists feeds it shows the shared icon (UI-02).
  - **Off:** the partner still **sees** the list, read-only, for as long as the couple exists (regardless of VIS-02), but cannot edit it. In their Lists feed it is a read-only list with a lock, in every state (UI-02).
- **CPL-03** On a shared list, the partner can do everything the owner can except delete it and change the share switch:
  - rename it;
  - add or remove meals and change servings;
  - add extra items;
  - check items off;
  - start and finish shopping.
- **CPL-04** The privacy settings (VIS-02) **never hide anything from the user's own partner**: while the couple exists, the partner always sees the user's meals and all of the user's lists (unshared ones read-only, CPL-02).
- **CPL-05** Either partner can end the couple at any time.
  - Every list stays with its **creator**, including history. The other person can no longer edit it, and sees it read-only only if the creator's lists are public (VIS-02).
  - The share switch is turned off on all lists of both users, so a later new couple shares nothing automatically.
  - Meals of the ex-partner that are now invisible to the other user are detached from that user's lists (LIST-15).
- **CPL-06** Meals always stay separate per user, also within a couple.
- **CPL-07** If a partner is **deactivated** (ADM-02), the couple and all shared lists stay, and the other partner can end the couple. Pending couple requests of the deactivated user are cancelled.

### 4.3 Privacy and visibility (VIS)

- **VIS-01** By default everything a user creates is visible to all users of the instance.
  - Ingredients are always shared.
  - Meals and lists belong to their owner.
- **VIS-02** Each user has two privacy switches, **meals public** and **lists public**. Both default to on (public). When a switch is off:
  - other users cannot see those meals or lists. The partner still sees all of the user's meals and lists (CPL-02, CPL-04);
  - the user disappears from the matching **user filter** of everyone except their partner: from the user filter on Meals (MEAL-10) for the meals switch, from the user filter on Lists (UI-02) for the lists switch.
- **VIS-03** Other people's public lists are **read-only**. They offer **"Copy to my lists"**, which creates a new draft with the same servings and extra items, and the same meals **as far as the copier can see them** (VIS-06).
- **VIS-04** Other people's visible meals can be viewed, added to one's own lists (LIST-03) and copied (MEAL-08). Only the owner can edit or delete a meal.
- **VIS-05** Photos are only served to users who are allowed to see the meal.
  - Photo URLs are unguessable and signed.
  - They expire after 1–2 hours.
  - A URL without a valid signature does not work.
- **VIS-06** When someone views a list that contains a meal **they cannot see** (e.g. a partner's private meal on a public list):
  - the meal appears only as "Private meal (*N* servings)", with no name, photo, link or source details;
  - the aggregated lines are still shown, because ingredients are shared data.

  "Copy to my lists" and "Shop again" leave out meals the acting user can't see or that no longer exist, and say how many were left out.

### 4.4 Reference data: categories, units, cuisines, tags (REF)

- **REF-01** **Categories** are seeded once, globally, with translation keys, in a default German-supermarket walking order. The seed list is in the [appendix](#appendix-a--seed-data).
  - Admins can **reorder** categories to match the store.
  - Adding or renaming categories needs a new app version.
  - `Other / Sonstiges` always exists.
- **REF-02** **Units:** `g`, `kg`, `ml`, `l`, `piece`, `tbsp`, `tsp`. They are fixed and shown translated (`Stk.`/`pcs`, `EL`/`tbsp`, `TL`/`tsp`).
  - Conversions: 1 kg = 1000 g, 1 l = 1000 ml, 1 tbsp = 15 ml, 1 tsp = 5 ml.
- **REF-03** **Cuisines:** a seeded, translated pick-list. Any user can add further cuisines as plain text. A meal has 0 or 1 cuisine.
- **REF-04** **Tags:** free text, 0 or more per meal, from one shared pool with autocomplete. Unique ignoring case and umlauts. Not translated.

### 4.5 Ingredients (ING)

- **ING-01** Ingredients are **shared by all users**. Any user can create one and **edit** any one, like a household wiki. The app records and shows "created by" and "last changed by".
- **ING-02** An ingredient has:
  - a **name** (stored as typed, not translated). Names don't have to be unique: "Milch" can exist once per brand, and by hand;
  - an optional **brand** and an optional **barcode** (EAN/UPC, unique when set), plus the pack size as information;
  - a **category** (required, default *Other*);
  - a **base unit** (`g` or `ml`, required, default `g`);
  - an optional **weight of one piece** in g (e.g. egg = 60 g);
  - an optional **density** in g per ml;
  - its nutrition values (NUT-02), all optional.
- **ING-03** Search covers the name and the brand and ignores case, umlauts and accents: `apfel`, `Äpfel` and `aepfel` all find "Äpfel". Everywhere an ingredient is shown, the brand follows the name ("Milch (Weihenstephan)"). When a user creates an ingredient, a "similar ingredient already exists" hint is shown; it doesn't block creating it. The **Ingredients tab**:
  - is one A–Z list in **dictionary order** by name, then brand. Dictionary order ignores case and accents and sorts ä/ö/ü as a/o/u and ß as ss, so "Äpfel" sits next to "Apfel". With a search, the best matches come first ("Milch" above "Buttermilch"), then the same order;
  - shows in each row the name with the brand and the barcode icon, and the category and base unit in the grey line ("Milchprodukte & Eier · ml");
  - offers several categories in its filter panel (UI-01); an ingredient matches **any** of them;
  - turns its "Neue Zutat" tile into "„Quitten“ anlegen" while a search text is present, which opens "Neue Zutat" with that name filled in.
- **ING-04** An ingredient can be created by hand (name only is enough), from a **barcode scan**, or from an **Open Food Facts name search** (BAR-11). Scanned or searched ingredients keep their Open Food Facts origin for refreshes (BAR-05). An existing ingredient without a barcode can be given one later (a scan in the shop: "this is already in MealMate").
- **ING-05** Only admins can **delete** an ingredient, and only while nothing references it. Otherwise admins can **merge** duplicate ingredients ("merge A into B"): every meal and list reference is moved to B, and A is deleted (A's barcode moves to B if B has none).
- **ING-06** Ingredients created by a user who is later deleted stay, shown as created by "deleted user".

### 4.6 Nutrition (NUT)

- **NUT-01** Tracked nutrients: **kcal, protein, carbohydrates, sugar, fat**, per 100 g or 100 ml. Adding a nutrient later must only require adding it to one registry in code, one database migration and translations (see plan).
- **NUT-02** An ingredient's value for each nutrient is its own stored value (typed, or from Open Food Facts); a missing value is **unknown**, and unknown is never treated as 0.
- **NUT-03** A meal's nutrition is the sum over its ingredients (amount converted to the base unit × value per 100). It is shown **per meal** and **per serving** (total ÷ `servings`).
- **NUT-04** If any ingredient value is unknown or an amount can't be converted, the total shows what can be calculated plus an **"incomplete"** marker. The marker names the missing ingredients or fields.
- **NUT-05** Conversions needed for nutrition:
  - `piece` uses the ingredient's piece weight;
  - g↔ml uses its density;
  - spoons of a g-based ingredient without density are counted as 1 g/ml and marked **"estimate"**.
- **NUT-06** Nutrition is computed when requested, not stored, so ingredient changes show up everywhere immediately.

### 4.7 Barcode scanning and Open Food Facts (BAR)

- **BAR-01** A **scan button** is available in the ingredient picker of the meal form. For now that is its only place: the Ingredients tab has none until creating ingredients is redesigned. It uses the phone camera (EAN-13, EAN-8, UPC-A, UPC-E). The barcode can also be typed in by hand as a fallback. The ingredient form's barcode field keeps its own scan button, which only fills in the number.
- **BAR-02** Lookup order: own database first, then OFF. A known barcode goes straight to its ingredient.
- **BAR-03** For an unknown barcode, the app opens the **ingredient form prefilled** with the OFF product (name in the user's language if available, brand, pack size, category guess, nutrition, barcode); the user can correct anything and saves with **one tap**. If OFF doesn't know it, the same form opens with only the barcode filled in. Alternatively the barcode can be attached to an existing ingredient without a barcode.
- **BAR-04** Values the user changed or typed are marked as **user-edited per field** and are never overwritten automatically.
- **BAR-05** Ingredients from OFF are refreshed when older than **30 days** (configurable):
  - in the background when the ingredient is scanned or opened;
  - by a nightly job.
- **BAR-06** When a refresh returns new values:
  - fields that were not user-edited update silently;
  - for user-edited fields, the app shows a hint: "Open Food Facts has newer values: kcal 165 → 158 [Apply] [Ignore]".
- **BAR-07** When OFF is unreachable, or the product was removed there, the cached values stay and the next scheduled refresh tries again.
- **BAR-08** OFF usage rules:
  - a descriptive User-Agent (`MealMate/<version> (<contact>)`);
  - at most 10 product requests per minute from the server;
  - text search (BAR-11) only on an explicit user action, never as-you-type, with its own smaller rate limit and a 24-hour cache.
- **BAR-09** Attribution "Nutrition data: Open Food Facts (ODbL)" with a link is shown wherever OFF data is displayed and on the About page. Product images from OFF are not stored or shown in v2.0.
- **BAR-10** OFF data is **untrusted input**. It is validated and sanitised on the server:
  - text lengths are capped;
  - control and bidi characters are removed;
  - nutrient values must be finite and plausible, otherwise they are dropped.

  It is only ever rendered as text.
- **BAR-11** **Name search:** in the ingredient form and the ingredient picker, "Search Open Food Facts" searches OFF for the typed text (products sold in Germany). Results show name, brand, pack size and kcal, and mark products already in MealMate. Choosing one fills the ingredient form like a scan (BAR-03), barcode included.

### 4.8 Meals (MEAL)

- **MEAL-01** Only the **name** is required. Everything else is optional, with no minimum number of ingredients.
- **MEAL-02** A meal has:
  - a name;
  - 0 or more **ingredient rows** (ingredient, optional amount, optional unit, optional note such as "to taste");
  - **instructions** (multi-line plain text);
  - **one photo**;
  - a **source link**;
  - **servings** (whole number ≥ 1, default 1);
  - 0 or 1 cuisine;
  - 0 or more tags.
- **MEAL-03** In the meal form, a missing ingredient can be **created inline**; a name alone is enough (ING-04). The scan button is available there too.
- **MEAL-04** **Photo:**
  - taken with the camera or picked from the library;
  - shrunk on the phone before upload (about 1600 px);
  - on the server it is rotated upright, re-encoded (so all metadata including **GPS** is removed), and stored with a thumbnail under a random name;
  - JPEG, PNG and WebP up to 10 MB are accepted.
- **MEAL-05** **Source link:** any `http(s)` URL (other schemes are rejected). It is shown as a prominent button that opens the link in Safari / a new tab. There is no link preview.
- **MEAL-06** Meal detail shows the photo, nutrition per meal and per serving (NUT-03/04), ingredients, instructions, source button, owner, and "based on *X* by *Y*" for copies.
- **MEAL-07** Only the **owner** can edit or delete a meal. Deleting a meal never silently changes other lists: wherever it is used on a list that isn't frozen yet, it is **detached** (LIST-15).
- **MEAL-08** **Copy** (one tap, on any meal visible to the user) creates an independent meal owned by the copier. It includes ingredients, amounts, instructions, cuisine, tags, source link and its own copy of the photo, and it remembers the original ("based on X by Y"). The reference disappears when the original is deleted or becomes invisible.
- **MEAL-09** The **Meals tab**:
  - has the search field (name, tag, cuisine) at the top of its pinned block (UI-01). While a search text is present, the "Neues Gericht" tile reads "„Lasagne“ anlegen" and opens the meal form with that name filled in;
  - shows in each row the owner's initial in a round marker, as on Lists (UI-02), and the cuisine in the grey line;
  - offers in its filter panel several cuisines (a meal matches **any** of them), several tags (a meal must have **all** of them) and the user filter (MEAL-10);
  - sorts meals A–Z in dictionary order (ING-03), so "Äpfel im Schlafrock" sits next to "Apfelstrudel".

  The list-building picker ("Gerichte hinzufügen") shows "recently used" meals first. It offers every meal the user can see, whatever the user filter on Meals says, shows the owner's initial marker in its rows, and opens without the keyboard.
- **MEAL-10** The **user filter** on Meals is a group of checkboxes in the filter panel, one per user whose meals are visible, including oneself and the partner. Each checkbox shows or hides that user's meals. It is saved per user on the server, separately from the user filter on Lists (UI-02), so it follows them across devices. The meal picker ignores it (MEAL-09).

### 4.9 Shopping lists: building (LIST)

- **LIST-01** "**+ New list**" immediately creates a draft and opens the meal picker. A user can have any number of drafts, and a draft can stay forever.
- **LIST-02** **Name and date:** a list can be renamed.
  - The display is always `<name> (<creation date>)`, e.g. "Grillabend (26.09.2026)".
  - Without a custom name, it shows the translated default in the **viewer's** language, e.g. "Einkaufsliste (26.09.2026)".
- **LIST-03** **Adding meals:** any meal visible to the user (own, partner's or other users' public meals) can be added directly; no copy is needed. A meal can be created on the spot from the picker.
- **LIST-04** **Servings:**
  - Each meal on a list has a **servings** count (whole number ≥ 1) with +/- buttons.
  - It starts at the meal's own `servings` value.
  - The scale factor is `list servings ÷ meal servings`.
  - A meal appears at most once per list; adding it again raises its servings.
- **LIST-05** The list view shows at the **top** the meals with their servings, and **below** the aggregated lines grouped by category in category order (AGG).
- **LIST-06** **Extra items** are added through one input with autocomplete over ingredients:
  - picking an ingredient adds a linked extra item (optional amount and unit) that merges with the same ingredient from meals;
  - anything else becomes a **free-text** item with an optional free-text amount. It goes into *Other* unless the user picks a category.
- **LIST-07** In a draft, a calculated line can be **removed for this list only** (swipe), e.g. "still have rice". It moves to a collapsed "Removed" section and can be restored. Nothing is remembered for future lists (there is no pantry logic).
- **LIST-08** Tapping a line shows which meals and extra items it comes from. Meals the viewer can't see show as "Private meal" (VIS-06).
- **LIST-09** Every change is saved to the server immediately. A draft can be continued on another device, even after closing the app or restarting the phone. Offline behaviour is covered in SYNC.
- **LIST-10** **List states:**

  | State | Meaning |
  |---|---|
  | `draft` | Being planned. Lines are computed live from the current meals (except detached ones, LIST-15). |
  | `shopping` | "Start shopping" pressed. Meal ingredients are frozen (LIST-11) and items are checked off. |
  | `done` | "Finish shopping" pressed. Read-only. Stays in the Lists feed, marked as done (UI-02, SHOP-05). |

- **LIST-11** **Freezing:** on "Start shopping", each meal's current ingredients are copied into the list, together with the ingredient data needed to calculate them (unit conversions, category).
  - From then on, edits to the meal, deletion of the meal, or wiki edits of the ingredients no longer change this list or its history.
  - A meal or linked extra item added while shopping is frozen at the moment it's added.
- **LIST-12** **Editing while shopping** (online only): add or remove meals, change servings, add or remove extra items. This lets a partner at home change the list while the other person is in the store.
  - A new line appears unchecked and marked "new".
  - A **checked** line becomes **unchecked** again when it later needs more:
    - any of its amounts grows, and the difference is shown per unit (e.g. "+300 g", "+2 Stk.");
    - a new unit or a part without an amount is added;
    - a free-text item's text or amount is edited (shown as "changed").
  - A checked line that needs less stays checked.
- **LIST-13** **Delete:** the owner can delete a list in any state, after a confirmation.
- **LIST-14** **Reminder:** the last row of every list is a random, friendly reminder, e.g. "Nichts vergessen? Klopapier? Salz?" / "Didn't forget anything? Toilet paper? Salt?".
  - It comes from a pool of about 10 per language, kept in the translation files.
  - It stays the same for a given list.
  - The same reminder appears in the finish dialog (SHOP-04).
- **LIST-15** **Detached meals:** when a meal on a not-yet-frozen list is **deleted** by its owner, or **stops being visible** to the list's owner (privacy switched off, couple ended, owner's account deleted), it is detached from that list:
  - its current ingredients are frozen into the list (as in LIST-11), so the list keeps working;
  - it is marked "no longer available", and the list owner can remove it.

  It is never removed silently. Lists that are already frozen are unaffected.

### 4.10 Aggregation, units and rounding (AGG)

- **AGG-01** All amounts, conversions, aggregation, rounding and nutrition are computed in the **backend**. The frontend only formats numbers for the locale.
- **AGG-02** A line merges all parts for the **same ingredient**: the scaled amounts from meals plus linked extra items. Free-text extra items are never merged.
- **AGG-03** **Merging rules:**
  - Units of the same kind always merge: g + kg → mass; ml + l + tbsp + tsp → volume; pieces.
  - Different kinds merge only when the ingredient has the needed conversion (piece weight, density). The result is shown in the ingredient's base unit.
  - Otherwise the parts are shown side by side on one line: "500 g + 2 Stk.".
  - Parts without an amount ("salt, to taste") appear as "Salz" with no amount, or as "+ etwas / + some" next to other parts.
- **AGG-04** **Display rounding** (calculations keep full precision):
  - g and ml → whole numbers; from 1000 shown as kg or l with up to 2 decimals, trailing zeros removed;
  - pieces → rounded **up** to whole pieces;
  - lines made only of spoons → shown in tbsp (tsp ÷ 3), rounded to the nearest half, at least ½.
- **AGG-05** Aggregation results are deterministic for the same input. This matters for tests and for stable line identities used by check-off (SYNC).

### 4.11 Shopping mode and history (SHOP)

- **SHOP-01** Shopping mode shows big checkboxes (tap targets ≥ 44 × 44 pt).
  - Checked lines are struck through, get an icon and move into a collapsed **"In the cart"** section at the bottom.
  - Each checked line shows who checked it (initial).
- **SHOP-02** Extra items can be added quickly while shopping.
- **SHOP-03** The list shows a sync indicator (SYNC-07).
- **SHOP-04** **Finish:** "Finish shopping" opens a dialog with the reminder (LIST-14), "*N* items not checked", and two buttons: *Finish* and *Keep shopping*. When the last item is checked, the app offers to finish.
- **SHOP-05** **Done lists** stay in the Lists feed (UI-02), in their place by creation date, with a check and "gekauft am 26.09." (the day they were **finished**). There is no separate history page.
  - In an opened done list, checked lines count as bought; unchecked lines are shown greyed.
  - One's own done lists and shared ones have no lock. A shared done list shows like that in both partners' feeds while the couple exists (see CPL-05 for what happens after).
  - Done lists of other users, and the partner's unshared ones, are read-only lists with a lock.
- **SHOP-06** A done list offers two actions:
  - **"Shop again"** creates a new draft with the same meals (current versions), servings and extra items, all unchecked. Meals that are deleted or not visible are left out with a notice (VIS-06).
  - **"Reopen"** moves it back to *shopping*, in case *Finish* was tapped by mistake.

### 4.12 Offline use and sync (SYNC)

- **SYNC-01** MealMate is installable as a **Home Screen web app** (PWA).
  - After the first login, a one-time hint shows how to "Add to Home Screen".
  - The Safari tab and the Home Screen app are separate on iOS, each with its own storage and offline data. Reliable offline use is only guaranteed in the Home Screen app.
- **SYNC-02** **Local copy on the phone:** every time the app is opened (or comes to the foreground) with a connection, it stores a text-only copy on the phone of all lists the user can edit, in *draft* or *shopping* state (own and partner's shared ones).
- **SYNC-03** **Offline actions** in shopping mode:
  - check and uncheck lines;
  - add, rename and delete **free-text** extra items;
  - finish the list.

  Everything else needs a connection. The app shows an "offline" banner and disables those controls instead of pretending to save.
- **SYNC-04** **Survives closing:** offline actions are stored on the phone immediately and survive closing the app and restarting the phone. They are sent automatically, in order, the next time the app is open with a connection: at start, when it comes to the foreground, and when the connection returns. iOS does not allow web apps to sync in the background.
- **SYNC-05** **Safe to resend:** each offline action carries a unique ID, so sending it twice has no extra effect. Unsent actions survive an expired login and are sent after the **same** user logs in again. Logging out with unsent actions asks for confirmation first.
- **SYNC-06** **Conflicts:**
  - For check state, the **most recent tap wins**, compared by the time the tap happened, not the time it synced.
  - If one phone edits a free-text item and the other deletes it, the delete wins.
  - Items added on two phones are not merged automatically.
  - Check-offs made **before** a partner finished the list still count after it was finished.
- **SYNC-07** **Sync status indicator**, one of:
  - "Saved";
  - "Offline – *N* changes waiting";
  - "Can't reach MealMate – no signal or Tailscale off?".

  Actions not yet delivered look slightly faded. A banner appears if changes have been waiting for more than one hour.
- **SYNC-08** **Live updates:** while a list is on screen, the app checks for changes about every **5 seconds** and immediately when it returns to the foreground. Pull-to-refresh is available. There are no push notifications in v2.0.
- **SYNC-09** **Poor signal:**
  - The app shell (HTML, JS, CSS, icons, translations) is cached, and the app opens from it **immediately**, also on a connection that is up but carries nothing ("lie-fi").
  - Cached lists are shown first and refreshed in the background.
  - Server requests give up after a few seconds and are treated as "can't reach MealMate". The app never hangs on a blank screen.
  - Screens other than cached lists show a friendly offline message.
- **SYNC-10** **Local data lifecycle:**
  - Logging out deletes the local list copy and cached profile; the outbox is deleted too, after the SYNC-05 confirmation.
  - When the server reports the session as revoked or the user as deactivated, the local copy and profile are deleted, and only that user's outbox is kept.
  - Queued actions are only ever sent with a session of the **same** user.
  - Lists the user lost access to disappear at the next sync.

### 4.13 Export (EXP)

- **EXP-01** Any list can be shared as plain text through the **native share sheet**, e.g. to Notes, WhatsApp or Messages. If no share sheet is available, the text is copied to the clipboard.
- **EXP-02** The export text:
  - uses the exporting user's language and number format;
  - has the list name and date first;
  - then the meals with their servings;
  - then the lines grouped by category (unchecked first);
  - then the reminder.
- **EXP-03** Export works offline for locally stored lists (SYNC-02).

### 4.14 Languages and formatting (I18N)

- **I18N-01** The UI is in **German and English**, with a language switch in settings. The choice is stored per user on the server. Adding a language must only require adding one translation file (plus seed translations).
- **I18N-02** Before login, the phone or browser language is used (German if it starts with `de`, otherwise English). The chosen language is saved at registration.
- **I18N-03** The backend never returns user-facing text. Errors are **codes** with parameters, e.g. `meal.not_found`, and the frontend translates them. Every error code must have a German and an English translation, enforced by a test.
- **I18N-04** Seeded data (categories, units, cuisines) and the reminder texts are translated through keys. User-created text (meal, ingredient and tag names, instructions) is never translated.
- **I18N-05** **Formats follow the UI language:**
  - German: `26.09.2026`, `1,5 kg`;
  - English: `26/09/2026`, `1.5 kg` (day first).

  Amount inputs accept both `,` and `.` and open the numeric keypad. Times are stored in UTC and shown in the phone's local time zone.
- **I18N-06** A test fails the build if a key exists in one language file but not the other, if a translation is empty, or if the `{placeholders}` differ between languages.

### 4.15 Administration (ADM)

- **ADM-01** The admin section (in *Me*) offers:
  - creating and revoking invites, and seeing their status (open / used by X / expired / revoked);
  - creating reset links;
  - listing users;
  - promoting and demoting admins;
  - deactivating, reactivating and deleting users;
  - reordering categories;
  - merging and deleting ingredients;
  - system info: app version, last successful backup, free disk space;
  - an **admin activity log** showing invites, reset links, role changes, deactivations, deletions and merges, each with who and when.

  At least one **active** admin must always remain, and admins cannot deactivate or delete themselves.
- **ADM-02** **Deactivating** a user:
  - blocks login immediately and ends all their sessions;
  - keeps their data and their couple (CPL-07), and their name is shown with "(deactivated)";
  - can be undone.
- **ADM-03** **Deleting** a user:
  1. First, the lists they share with a partner **move to the partner**.
  2. Then their meals are detached from all lists of other users, including the ones that just moved (LIST-15).
  3. Finally their meals, photos, remaining lists (including history), pending couple requests, and any unused invites or reset links issued for them are removed.

  Ingredients they created stay ("deleted user"). Copies other people made of their meals stay. The last active admin can't be deleted.
- **ADM-04** Admins have **no screen or endpoint** to view other users' private meals or lists, and cannot silently log in as another user.
  - The only way to take over an account is a reset link. That ends the user's sessions and is visible to them (ACC-10) and in the activity log.
  - Whoever runs the Pi can technically read the database and backups. The user guide says so.

### 4.16 App shell and navigation (UI)

- **UI-01** Mobile-first layout for iPhone, one-handed use.
  - **Tab bar:** a floating, frosted bar at the bottom with **Lists**, **Meals**, **Ingredients** and **Me**, as icons only; screen readers still read the tab names. It keeps a gap at both sides and above the bottom edge, also on iPhones without a home indicator, and taps beside it reach the content. The active tab gets a subtle lighter pill and a green icon with a thicker stroke, so colour is not the only signal. The bar stays visible while scrolling and its icons stay readable over meal photos, in light and dark mode.
  - **Tab screens** (Lists, Meals, Ingredients, Me) show no visible headline; each still has a heading that screen readers announce. Detail screens (a shopping list, a meal, an ingredient, the admin pages) keep their visible titles.
  - **Pinned block:** Lists, Meals and Ingredients have a frosted block at the top that stays put while scrolling. It holds a search field (not on Lists), a filter button and a green "Neu…" tile shaped like a row of that tab ("Neue Liste", "Neues Gericht", "Neue Zutat"). It appears at once and looks the same while the tab loads, when it is empty and when it is filled.
  - **Filter panel:** the filter button opens a panel that slides up from the bottom (without animation under Reduce Motion) with groups of checkboxes. Each change applies immediately. "Zurücksetzen" resets every group and "Fertig" closes the panel. The button shows how many groups are not at their default, also in its accessible name.
  - **Kept per tab:** the search text and the cuisine, tag and category choices stay until the app is closed, so opening an entry and coming back keeps them. The user filter and the state filter are saved on the server (UI-02, MEAL-10).
  - **Keyboard:** while the on-screen keyboard is open, in a pop-up or on a page, the tab bar and the update banner hide. Pop-ups fit into the space above the keyboard, so their last field and main button can be reached. Pinch-zoom is not mistaken for an open keyboard (A11Y-02).
  - At the largest iPhone text size, the pinned block, the filter panel and the tab bar show all their text and controls without clipping or overlap, wrapping where needed.
- **UI-02** The app opens on **Lists**: one **feed** of every shopping list the user can see (their own, their partner's shared and unshared ones, other users' public ones), in every state (draft, shopping, done). It is sorted by creation date, newest first, so a list never moves when it is edited, shopped or finished. The newest 30 come first, more as the user scrolls down.
  - **Row:** the list's name and date (LIST-02), "3 Gerichte · 5 Artikel", and a round marker with the owner's initial, also on one's own lists; screen readers read the marker as the owner's name. Icons, and texts after the counts, mark the kind of list; a row can have several (a shared list being shopped shows both icons):

    | List | Icon | Text |
    |---|---|---|
    | Own shared list | shared | "Geteilt mit <partner>" |
    | Partner's shared list | shared | "von <owner>, mit dir geteilt" |
    | Read-only list (no edit rights, in any state; CPL-02, VIS-03) | lock | "von <owner>" |
    | Being shopped | cart | |
    | Done list (SHOP-05) | check | "gekauft am <date>" |

    One's own unshared lists add no "von" text.
  - **Pinned block** (UI-01): the green "Neue Liste" tile, which creates a draft and opens the meal picker (LIST-01), and the filter button. There is no search field.
  - **Filter panel:** the **user filter**, one checkbox per user whose lists are visible, including oneself and the partner; unticking a user hides all of that user's lists, shared ones too. The **state filter**: "Entwurf", "Einkauf" and "Erledigt", all ticked by default. Both are saved per user on the server, so they follow the user across devices.
  - The first-login hints and the offline and sync notices sit below the pinned block and scroll away with the feed.
  - **Local copy:** until the feed's first page arrives, also online, the tab shows the local copy (SYNC-02, SYNC-09), sorted like the feed. **Offline** it shows only the local copy, whatever the saved user filter and state filter say, and disables the filter button and the "Neue Liste" tile. Read-only and done lists need a connection.
  - Opening a done list shows it read-only, with "Shop again" and "Reopen" (SHOP-06). An old link to the former history page leads to the Lists tab.
- **UI-03** Lists, Meals and Ingredients show their pinned block (UI-01) at once. Below it:
  - while the tab's first load runs, the loading placeholder;
  - on an empty tab, one short line ("Noch keine Listen" / "Noch keine Gerichte" / "Noch keine Zutaten"), with no icon, heading or button: the "Neu…" tile is the action;
  - when the search or the filters hide everything, "Keine Treffer" with a "Filter zurücksetzen" button, which clears the search text and resets every filter group.
- **UI-04** Dark mode follows the iPhone setting automatically.
- **UI-05** Branding: name **MealMate**, a green accent colour (from the v1 `#4CAF50` family), and a simple basket icon for the Home Screen and favicon. All colours are defined once as design tokens so the design can be re-skinned easily.
- **UI-06** The *Me* tab shows the version and a **"Source code (AGPL-3.0)"** link to the exact source revision being run (LIC-02). It also contains the OFF attribution (BAR-09).

## 5. Non-functional requirements

### 5.1 Platform and deployment (PLT)

- **PLT-01** **Target hardware:** Raspberry Pi 3 Model B v1.2 (4 × Cortex-A53, 1 GB RAM, 100 Mbit Ethernet), microSD card of **16 GB or more** (32 GB preferred), official 2.5 A power supply.
- **PLT-02** **OS:** Raspberry Pi OS Lite **64-bit**, headless, hostname `mealmate`, SSH with key only (no password login). The setup script also:
  - turns on **automatic updates** for Debian security, Raspberry Pi, Docker and Tailscale packages, with an automatic reboot at night when needed;
  - sets the system up to write as little as possible to the SD card: logs in RAM, capped Docker logs, `noatime`, compressed swap in RAM (zram) only;
  - enables the memory cgroup, so container memory limits work.
- **PLT-03** **Delivery:** the app runs as **one Docker container** from a prebuilt `linux/arm64` image on `ghcr.io`, started with Docker Compose. Nothing is built on the Pi. The Pi only installs images whose **signed build provenance** proves they were built by this repository's release workflow (SEC-12).
- **PLT-04** **Remote access** only via **Tailscale**:
  - Tailscale runs on the Pi's operating system, not in Docker.
  - Every user installs the Tailscale app and leaves it on (VPN On Demand keeps it connected).
  - The Pi is **shared** with each user (node sharing), so users can reach only the Pi.
  - No router ports are opened.
  - The Pi is **tagged** (`tag:mealmate`), so it acts as a server, not as the owner's device, and its key does not expire.
  - A tailnet policy allows shared users to reach only HTTPS on the Pi, allows the owner's devices to reach SSH and HTTPS on the Pi, and gives the Pi no access to any other device.
- **PLT-05** **HTTPS:**
  - HTTPS is provided by `tailscale serve`, with a browser-trusted certificate for `https://mealmate.<tailnet>.ts.net`.
  - This is the **only** address; there is no second LAN address, because each address would mean a separate login and separate offline data.
  - The app listens on `127.0.0.1` only.
- **PLT-06** Setting up a new SD card (initial install, card swap, disaster recovery) is **one documented, scripted procedure**: flash with Raspberry Pi Imager → download and run `setup.sh`, or `setup.sh --restore <backup>`. It takes about 30 minutes and is tested before go-live (OPS-07).
- **PLT-07** Host-side files (compose file, scripts, systemd units) are **versioned with the app**. Every successful update installs the matching version of them, so fixes to scripts reach the Pi automatically.

### 5.2 Security and privacy (SEC)

- **SEC-01** **The repository is public.**
  - No secret, key, certificate, password or personal data may ever be committed.
  - CI runs a secret scanner.
  - GitHub push protection is enabled.
  - The v1 self-signed key (`certs/key.pem`, public in git history) is considered compromised and is never reused.
- **SEC-02** Secrets live only in `/srv/mealmate/.env` on the Pi, readable only by root:
  - `MEALMATE_SECRET_KEY`, generated randomly by the setup script;
  - the healthchecks.io ping URLs.

  **No secret has a default value in code.** The app refuses to start without a secret key. Only the variables the app needs are passed into the container. The secret key can be **rotated** with one command (which logs everyone out).
- **SEC-03** **Authentication:**
  - short-lived access tokens (15 min, held in memory);
  - a rotating refresh token in an `HttpOnly; Secure; SameSite=Strict` cookie, stored hashed on the server;
  - sessions can be revoked on the server;
  - passwords hashed with bcrypt.

  Rotation tolerates lost responses and parallel refreshes (a short grace period), so poor signal never logs a user out. Role and active status are read from the database on every request, never trusted from the token.
- **SEC-04** **Authorization** is checked in the backend for every request and every object (owner / partner / public / admin), including meals embedded in lists (VIS-06). It is covered by API tests, including "user A can't read or change user B's private data".
- **SEC-05** **Rate limiting:**
  - login (per username + client);
  - registration and reset (per client);
  - uploads (per user);
  - barcode lookups (per user);
  - a general per-user request limit.

  The client address comes from `X-Forwarded-For`, which is set by `tailscale serve` and trusted only from the local address `tailscale serve` connects from.
- **SEC-06** **Security headers** on every response:
  - an explicit Content-Security-Policy, see plan § 5.3: no inline scripts, no `eval`, `wasm-unsafe-eval` only for the barcode decoder, same-origin connections only;
  - `X-Content-Type-Options`;
  - `Referrer-Policy: no-referrer`;
  - `frame-ancestors 'none'`;
  - `Cache-Control: no-store` on all API responses.

  Outgoing source links use `rel="noopener noreferrer"`.
- **SEC-07** **Uploads:**
  - only the JPEG, PNG and WebP decoders are allowed;
  - the real file type is checked, and size (≤ 10 MB) and pixel count (≤ 24 MP) are limited;
  - the image is always re-encoded, which strips metadata;
  - it is stored under a random name outside any web root.
- **SEC-08** **No personal data beyond what's needed:** no email addresses, and no tracking or analytics. **No third-party requests from the browser**, including the barcode decoder, which is served by the app itself. OFF is contacted only by the server.
- **SEC-09** The container runs as a **non-root** user with a read-only root filesystem (except the data volume), no Linux capabilities and no privilege escalation. It contains no dev tools. Host scripts running as root never follow symlinks in container-writable directories.
- **SEC-10** Invite codes, reset codes and refresh tokens:
  - are long random values (≥ 128 bit);
  - are stored as keyed hashes (HMAC);
  - are never written to logs.

  The server does not log request paths with codes, or query strings.
- **SEC-11** **Dependencies are kept current:**
  - Dependabot weekly, grouped;
  - CI fails on known high or critical vulnerabilities in runtime dependencies;
  - a weekly scheduled scan of the **published** image opens an issue when fixable vulnerabilities appear.

  There is a documented **security-patch procedure** (fix on the release branch → patch release → the Pi installs it the same night).
- **SEC-12** **Supply chain:**
  - all GitHub Actions are pinned to commit SHAs;
  - no workflow runs untrusted fork code with secrets;
  - release images get **signed build provenance**;
  - the Pi's updater verifies it before installing (PLT-03).

  The owner's GitHub account uses 2FA.
- **SEC-13** Everything from outside the household is **validated as untrusted**: OFF responses (BAR-10), uploads (SEC-07), source URLs (MEAL-05). User-supplied text is only ever rendered as text, never as HTML.

### 5.3 Backups, monitoring and updates (OPS)

- **OPS-01** **Backups every 6 hours** on the Pi. Each backup contains:
  - a consistent SQLite snapshot (made with SQLite's backup API, never by copying the raw file), integrity-checked;
  - the photos (stored incrementally: unchanged photos are hard-linked, not copied again);
  - `.env`;
  - the Pi's Tailscale identity and SSH host keys, so a restore keeps the same address, shares and host fingerprint;
  - a manifest with app version, time and checksums.

  A backup only becomes visible once it is complete.
- **OPS-02** **Retention** (on the Pi and on the Mac, about 17 regular backups):
  - the newest backup per day for 7 days;
  - plus the newest per week for 4 weeks;
  - plus the newest per month for 6 months.

  Backups made before an update, and manual ones, are kept for 7 days in addition.
- **OPS-03** **Off-Pi copy:** the owner's **Mac pulls** new backups automatically over Tailscale.
  - It runs every hour while the Mac is awake, via `launchd`, and catches up after sleep.
  - It uses a dedicated SSH key that is restricted on the Pi to **read-only** access to the backup folder.
  - It only fetches backups it has never fetched before, and never overwrites what it already has.
  - It applies the retention by its own receive times. It never deletes anything younger than 7 days, and stops and alerts if a pull looks abnormal (too many or too large new backups).
  - So a compromised Pi can neither delete nor overwrite the Mac's copies.
  - One command installs it on the Mac.
- **OPS-04** **Alerts** come from a free external dead-man's-switch service (healthchecks.io), by email; push via ntfy or Telegram is optional. Checks:

  | Check | Pinged by | Alert when |
  |---|---|---|
  | `heartbeat` | Pi, every 5 min, only if Tailscale is running **and** the app answers OK through its own HTTPS address | silent for 15 min: Pi, Docker, app, Tailscale/HTTPS or internet down |
  | `backup` | Pi, after each successful backup and each monthly test restore | a failure, or silent for 8 h |
  | `mac-pull` | Mac, after each successful pull | a failure (e.g. abnormal pull), or silent for 3 days |
  | `update` | Pi, after each nightly update run | a failure, a rollback or an unverifiable image, or silent for 2 days |
  | `disk` | Pi, every hour | free space below 20 % |
  | `image-scan` | GitHub Actions, after each weekly scan of the published image (SEC-11) | silent for 9 days, e.g. because GitHub disabled scheduled workflows in a quiet repo |

  Only the scripts' own short status output is sent to healthchecks.io, never app logs.
- **OPS-05** **Updates:**
  - The Pi follows the **version line** of its release, e.g. image tag `2.0`: bug-fix releases (`2.0.1`, `2.0.2`) are installed automatically at night, after their provenance is verified (SEC-12).
  - Moving to a new feature version (`2.1`) is a deliberate one-line change.
  - Before an update: a backup. After it: a health check. If that fails: **automatic rollback** (previous image plus pre-update database) and an alert. The Pi then waits for the next newer release.
  - A manual `update.sh` exists too.
- **OPS-06** Database migrations run automatically at container start. The entrypoint first saves a pre-migration snapshot whenever migrations are pending.
- **OPS-07** **Restore:**
  - `setup.sh --restore <backup>` runs on a freshly flashed card. It swaps in the saved Tailscale identity **before the Pi first logs in to the tailnet**, then restores `.env`, SSH host keys, the backup access key, database and photos.
  - The full procedure is rehearsed on a spare SD card before go-live.
  - A monthly automatic test restore of the latest backup is integrity-checked (OPS-04 `backup`).
- **OPS-08** A manual backup can be started with one command (and from the admin page) before planned maintenance, such as an SD card swap.
- **OPS-09** The old and the new SD card must never run at the same time. Both would claim the same Tailscale identity, so the runbook warns about this.
- **OPS-10** **Backups contain credentials** (secret key, Tailscale identity).
  - The Mac copy lives outside iCloud-synced folders, the Mac uses FileVault, and a Time Machine disk must be encrypted.
  - The runbook covers "Mac or backup lost": remove and re-add the Pi in Tailscale, rotate the secret key, replace the backup SSH key, regenerate the healthchecks.io URLs.

### 5.4 Performance and resources (PERF)

- **PERF-01** The container uses **< 200 MB RAM** when idle and < 300 MB under normal use on the Pi 3. It runs one app process, and background jobs run as short-lived commands.
- **PERF-02** On the Pi 3:
  - API responses for a list with 20 meals and 150 lines take < 300 ms (p95), also with 3 phones polling;
  - opening a cached list works instantly, even offline or on lie-fi.
- **PERF-03** Initial JavaScript is < 300 KB gzipped. The barcode decoder and other heavy parts are loaded only when needed.
- **PERF-04** The container is healthy within 60 s after start on the Pi 3, including migrations.
- **PERF-05** Password hashing takes about 250–500 ms on the Pi 3 (the bcrypt cost factor is tuned for this). CPU-heavy work (password hashing, image processing) never blocks other users' requests.
- **PERF-06** PERF-01/02/04 are measured on the real Pi **early**: skeleton in M1, lists at the end of the shopping milestone. They are not only checked at release time.

### 5.5 Accessibility (A11Y)

- **A11Y-01** Aim for WCAG 2.1 AA where it is cheap:
  - semantic HTML and a label on every input;
  - colour is never the only signal;
  - contrast checked in light and dark mode;
  - tap targets ≥ 44 × 44 pt.
- **A11Y-02** Text scales with the iPhone text-size setting (rem units). Pinch-zoom stays enabled. "Reduce motion" is respected.
- **A11Y-03** An automated accessibility check (axe) runs on the main screens in E2E tests.

### 5.6 Maintainability and frontend handoff (MNT)

- **MNT-01** The **frontend and backend are strictly separated**. The frontend talks to the backend only through the documented HTTP API (OpenAPI). The frontend's TypeScript API types are **generated** from the OpenAPI description, and CI fails if they are out of date.
- **MNT-02** The frontend does **no domain calculations** (AGG-01). It formats data and handles UI state, the offline queue and export text.
- **MNT-03** A frontend developer can do the following on a laptop with one command each, without the Pi:
  - run the full stack with hot reload and demo data (`make dev` with `seed-demo`);
  - run the end-to-end suite (`make e2e`).
- **MNT-04** Conventions are documented from the start (M0) in `CONTRIBUTING.md` and `frontend/README.md`:
  - all strings go through i18n keys;
  - API calls only through `src/api/`;
  - interactive elements get accessible names and test IDs, kept in one file;
  - UI building blocks live in `src/components/ui/`.
- **MNT-05** UI building blocks (dialogs, sheets, dropdowns, toasts, chips) come from **shadcn/ui**, whose source is copied into the repo, so it can be restyled freely without lock-in. Styling uses Tailwind design tokens.
- **MNT-06** Adding a nutrient, a unit conversion, a category, a cuisine or a language follows a documented checklist.

### 5.7 Testing and quality gates (QA)

- **QA-01** **Backend:**
  - `pytest` unit and API tests;
  - **≥ 85 % line coverage** enforced in CI;
  - unit conversion, aggregation, servings scaling, rounding and nutrition aim for ~100 %, using table-driven tests plus property-based tests (Hypothesis);
  - concurrency tests for list operations (many parallel writes, none lost).
- **QA-02** **Migrations:**
  - every Alembic migration upgrades and downgrades cleanly from an empty database;
  - migrations are also run against a **database filled with demo data**, and no rows may be lost;
  - the models match the latest migration (no pending autogenerate diff).
- **QA-03** **Frontend:** Vitest for logic (API client, number parsing and formatting, offline queue, export text, i18n completeness) and for decoding sample barcode images.
- **QA-04** **End-to-end** tests in **Python (pytest-playwright)** against the built container, in **Chromium and WebKit** with an iPhone viewport, on every pull request. Covered flows:
  1. register via invite;
  2. login, refresh and logout;
  3. create an ingredient from a typed barcode, with OFF replaced by a fake server;
  4. create a meal and check its nutrition;
  5. copy another user's meal;
  6. build a list from meals with servings plus extra items, and check aggregation and category order;
  7. check items off offline and see them sync after reconnecting;
  8. export through a stubbed share sheet;
  9. the privacy toggle hides a user;
  10. switch language between German and English;
  11. couple sharing: the partner sees and checks off a shared list.

  The tests also assert that no request leaves the app's origin (SEC-08). Browser limitations of the test setup (e.g. Secure cookies over plain HTTP in WebKit) are handled as described in plan § 9 and covered by the manual check (QA-06).
- **QA-05** E2E tests find elements by role, accessible name or test ID, never by CSS classes, so the frontend can be restyled without breaking tests.
- **QA-06** Before every release tag, a **manual checklist on a real iPhone** (about 15 minutes):
  - camera scan;
  - share to Notes and invite sharing;
  - offline and lie-fi check-off and sync;
  - Home Screen install and staying logged in after a restart;
  - dark mode;
  - typing into the last field of every pop-up with a text field, and reaching its main button with the keyboard up;
  - the tab bar and the update banner hiding while typing, in pop-ups and in page fields;
  - the frosted tab bar and pinned block staying readable over meal photos, in light and dark mode.
- **QA-07** **Linting and formatting** are enforced in CI:
  - backend: ruff (lint and format) and mypy;
  - frontend: eslint, prettier and `tsc`.

### 5.8 Licensing and repository (LIC)

- **LIC-01** The project is licensed under **AGPL-3.0-or-later** (changed from GPL-3.0; owner decision Q-1). All code so far is by the owner, so no consent from others is needed.
- **LIC-02** The running app shows its version and links to the exact source commit (AGPL § 13). Images are only built by CI from the public repository.
- **LIC-03** Third-party licences are respected:
  - OFF data is ODbL (attribution shown; a derived database may only be shared under ODbL);
  - dependencies are MIT/BSD/Apache-compatible.

  A licence check runs in CI.

## 6. Postponed / future ideas

These are not in v2.0. The data model should not make them hard.

| Idea | Note |
|---|---|
| One-off adjustment of a meal's ingredient amounts when adding it to a list | e.g. 250 g instead of 200 g chicken for this list only |
| Package sizes and rounding up to whole packs | the product's pack size (OFF `product_quantity`) is already stored |
| Receipt photo → local OCR → purchased items and prices | the Pi 3 is too weak; run the OCR as a separate worker on stronger hardware |
| Price tracking, cost analytics, long-term statistics | |
| Multiple households on one server | not needed now: "public" means everyone on the server |
| Push notifications (e.g. "Anna added milk") | needs Web Push and the Home Screen app |
| Category order per store (Rewe vs Lidl) | |
| More nutrients (fibre, salt, …) and more languages | planned extension points (NUT-01, I18N-01) |
| Scan a barcode to check an item off in the store | |
| Public access without the Tailscale app (Tailscale Funnel) | would need extra hardening |
| Storybook / visual regression tests for the frontend developer | |
| Admin-editable categories, cuisines and reminder texts | |

## 7. Decision log

| # | Decision | Why |
|---|---|---|
| D-01 | Python/FastAPI backend, React + TypeScript + Vite frontend, SQLite | Owner's main language; same family as BUGSI; Java offers nothing extra and is heavy on 1 GB RAM; SQLite suits ≤ 10 users on a Pi 3 |
| D-02 | Tailscale with node sharing plus `tailscale serve` HTTPS | free; nothing exposed to the internet; trusted HTTPS, which the iPhone camera, share sheet and offline mode need |
| D-03 | Images built by GitHub Actions and published to ghcr.io, **only from release branches** | reproducible; native arm64 runners; hotfixes on `release/X.Y` |
| D-04 | Clean v2 rewrite; v1 archived as a tag; start with an empty database | v1 structure unsuitable; no data to migrate |
| D-05 | Ingredients shared and wiki-editable; meals owned, viewable and copyable; lists owned and shareable within a couple | household use with personal meal collections |
| D-06 | ~~Generic ingredient + linked barcode products, with nutrition = per-field average~~ — replaced by D-21 | |
| D-07 | Servings = "the recipe makes *N*" (default 1); lists scale by the chosen servings | covers both "per serving" and "whole recipe" |
| D-08 | Lists freeze meal ingredients at "Start shopping" | history stays true; check-off has stable lines |
| D-09 | No households now | single persons and couples are enough; can be added with a migration later |
| D-10 | Offline limited to check-off, free-text items and finishing | everything else needs server-side calculation (AGG-01) |
| D-11 | 5-second polling instead of a live connection | nearly free on a Pi 3; no reconnect handling on locked iPhones |
| D-12 | Mac pulls backups; healthchecks.io dead-man's switch for alerts | no cloud storage needed; a dead Pi can't send its own alert |
| D-13 | Pi follows the version line (`2.0`) with automatic rollback | hotfixes arrive automatically; migrations of feature versions are applied deliberately |
| D-14 | E2E tests in Python | owner's language; the frontend developer only has to keep the test IDs stable |
| D-15 | AGPL-3.0-or-later (Q-1) | hosted modified copies must share their source; standard GNU wording |
| D-16 | Open Food Facts API v3, ≤ 10 requests/min | v2 was deprecated in June 2026; OFF allows 15 product reads/min per IP |
| D-17 | When a user is deleted, the lists they share with a partner move to the partner | accepted default D15 in the planning conversation; the partner keeps their shopping history |
| D-18 | A meal that is deleted or becomes invisible is *detached* from lists (frozen copy + notice), never silently removed (owner decision Q-3) | consistent with "lists keep a snapshot"; no surprises in someone else's plan; no private data leaks |
| D-19 | "Shared with partner" switch: on = partner sees and edits; off = partner keeps read-only access while the couple exists (owner decision Q-2) | privacy never hides anything from the partner; the switch only controls editing and whether the partner gets the list in their offline copy |
| D-20 | Retention 7 daily / 4 weekly / 6 monthly (≈ 17), on Pi and Mac alike | as agreed by the owner; 6-hourly backups only reduce data loss on the current day |
| D-21 | One kind of ingredient: typed by hand or from OFF (barcode or name search), with an optional brand and barcode and its own values; different brands are different ingredients and separate shopping-list lines (2026-09-28, replaces D-06) | a new user has nothing to scan; creating from a scan or search must be one step; exact values per product instead of averages |
| D-22 | Tab screens without a visible headline (screen readers still get one). Lists, Meals and Ingredients share a frosted pinned block: a search field (not on Lists), a filter button and a green, row-shaped "Neu…" tile that offers "„<text>“ anlegen" while a search text is present. An empty tab shows one short line; a search or filter that hides everything shows "Keine Treffer" with "Filter zurücksetzen" (2026-10-02) | the tab bar already says where you are; search, filter and "Neu…" sit in the same place on every tab, one tap away; fewer sentences to read on a phone |
| D-23 | Filters move into a panel that slides up from the bottom: checkbox groups that apply immediately, "Zurücksetzen" for every group and "Fertig"; the filter button counts the groups not at their default. Several cuisines match as "any", several tags as "all", several categories as "any". The search text and the cuisine, tag and category choices are kept in memory per tab until the app closes (2026-10-02) | uncluttered tabs with filters in thumb reach; the count explains missing entries; two cuisines should widen the list, two tags narrow it; nothing to clean up in URLs or browser storage |
| D-24 | One Lists feed replaces the "Continue shopping" card, the drafts, the history page with its weekly groups and "Others' lists": every list the user can see, in every state, including done lists of every visible owner; newest created first (ties by id), 30 per page. The old history address leads to the Lists tab (2026-10-02) | one place to look; an order that never changes after a list is created, unlike "most recently edited"; the tab opens fast even after a year of shopping |
| D-25 | List rows mark the owner with an initial in a round marker (own lists too) and the kind of list with icons: shared, a lock for a read-only list, a cart while shopping, a check plus "gekauft am" when done. The lock means "no edit rights", whatever the state, so one's own and shared done lists get none (2026-10-02) | whose list it is shows at a glance instead of in spelled-out text; "read-only" keeps its glossary meaning and doesn't just mean "finished" |
| D-26 | The user filter on Lists covers every list one can see, one's own and the partner's shared lists included, and offers oneself as a choice; a saved state filter (draft, shopping, done) sits next to it. Offline, both are ignored and the tab shows the local copy. The meal picker ignores the user filter on Meals (2026-10-02) | the feed mixes every kind of list, so the filter must reach all of them; done lists pile up; filters follow the user across devices; the shopping list must never disappear in the shop, and the picker must never look mysteriously empty |
| D-27 | Meals and ingredients sort in dictionary order, by a key built from the original name (lowercase, ä/ö/ü → a/o/u, ß → ss, accents stripped), not from the `ae`-style normalized name. The Ingredients tab becomes one A–Z list (best match first while searching) with category and base unit in each row instead of category groups, and loses its scan button until creating ingredients is redesigned (2026-10-02) | "Äpfel im Schlafrock" belongs next to "Apfelstrudel"; folding "ae" back would also change real letter pairs ("Quelle", "Feuer", "Aloe"); people look for an ingredient by its name; the row still shows where it sorts on the shopping list |
| D-28 | A floating, frosted tab bar with icons only (names for screen readers); the active tab gets a lighter pill and a green icon with a thicker stroke. The tab bar and the update banner hide while the keyboard is open, and pop-ups fit into the visible area above it. The keyboard is detected from the visual viewport, ignoring pinch-zoom; no viewport-meta or VirtualKeyboard approach and no iOS "Liquid Glass" (2026-10-02) | the owner wants a lighter, see-through bar; on the iPhone the keyboard hid the Save buttons of pop-ups and the tab bar rode up above it; iOS supports neither the viewport-meta setting nor the VirtualKeyboard API, and the CSP rules out inline scripts |

## 8. Owner decisions

| # | Question | Answer (2026-09-26) |
|---|---|---|
| Q-1 | Licence variant: **AGPL-3.0-or-later** (the standard GNU wording, which allows future AGPL versions) or **AGPL-3.0-only**? | **AGPL-3.0-or-later** |
| Q-2 | "Shared with partner" switched **off**: should the partner lose access to that list, like any other user (D-19), or keep read-only access, with the switch only controlling editing? | **Keep read-only access while the couple exists** |
| Q-3 | A meal that is deleted or becomes invisible: should it be *detached* from other people's lists (frozen copy + "no longer available" notice, D-18), or simply removed from their drafts? | **Keep the frozen copy** |

Items that can only be settled on the real hardware are tracked as open points in [plan § 15](plan.md#15-open-points-to-verify-during-implementation).

## Appendix A — Seed data

**Categories** (default order; key → German / English):

| # | Key | Deutsch | English |
|---|---|---|---|
| 1 | `fruit_vegetables` | Obst & Gemüse | Fruit & vegetables |
| 2 | `bread_bakery` | Brot & Backwaren | Bread & bakery |
| 3 | `dairy_eggs` | Milchprodukte & Eier | Dairy & eggs |
| 4 | `cheese` | Käse | Cheese |
| 5 | `meat_fish` | Fleisch & Fisch | Meat & fish |
| 6 | `sausage_deli` | Wurst & Aufschnitt | Sausage & deli |
| 7 | `plant_based` | Tofu & pflanzliche Alternativen | Tofu & plant-based |
| 8 | `pasta_rice_grains` | Nudeln, Reis & Getreide | Pasta, rice & grains |
| 9 | `canned_jars` | Konserven & Gläser | Canned & jarred |
| 10 | `sauces_spices_oils` | Soßen, Gewürze & Öle | Sauces, spices & oils |
| 11 | `baking` | Backzutaten | Baking |
| 12 | `breakfast_spreads` | Frühstück & Aufstriche | Breakfast & spreads |
| 13 | `snacks_sweets` | Süßes & Snacks | Snacks & sweets |
| 14 | `frozen` | Tiefkühl | Frozen |
| 15 | `drinks` | Getränke | Drinks |
| 16 | `household_hygiene` | Drogerie & Haushalt | Household & toiletries |
| 17 | `other` | Sonstiges | Other |

**Cuisines:** german, italian, french, greek, turkish, mediterranean, american, mexican, indian, chinese, japanese, thai, other (translated). Users can add more as plain text.

**Reminder texts:** about 10 per language, written in `de.json` and `en.json` (they are not literal translations of each other).
