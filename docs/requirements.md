# MealMate v2 — Requirements

| | |
|---|---|
| Status | Agreed baseline, 2026-09-26 |
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
  - in the supermarket, with poor or no mobile signal, for checking items off.
- **Effort principle:** the least possible effort for users. Setup happens once (Tailscale app, one invite link, "Add to Home Screen"). Everyday use must not require toggles, logins or manual syncing.

## 3. Glossary

| Term | Meaning |
|---|---|
| **Ingredient** | A generic, shared food item (e.g. "Hähnchenbrust"). It has a category, a base unit (g or ml) and nutrition values per 100 g/ml. |
| **Product** | A specific barcode (EAN/UPC) item (e.g. one brand's chicken breast), linked to exactly one ingredient. It usually comes from Open Food Facts. |
| **Meal** | A recipe owned by one user: ingredients with amounts, instructions, photo, source link, and "makes *N* servings". |
| **Serving** | One portion. A meal's `servings` value is how many portions its ingredient amounts make (default 1). |
| **Shopping list** | A list owned by one user, built from meals (each with a chosen number of servings) plus extra items. |
| **Line** | One row on a shopping list after aggregation, e.g. "Onions 500 g". It merges the same ingredient from all meals and extra items. |
| **Extra item** | Something added to a list by hand. It is either linked to an ingredient ("1 l milk") or free text ("Birthday candles"). |
| **Couple / partner** | Two users who have agreed to share shopping lists. Each user can be in at most one couple. |
| **Admin** | A user with the admin role: manages accounts, invites and shared reference data. |
| **OFF** | Open Food Facts, the open product database (openfoodfacts.org). |

## 4. Functional requirements

### 4.1 Accounts and sign-in (ACC)

- **ACC-01** Registration is only possible with a valid **invite**. There is no open sign-up.
- **ACC-02** Only admins create invites. An invite:
  - is single-use and valid for 7 days (configurable);
  - can be revoked;
  - always creates a normal *user* (an admin can promote the user later).
- **ACC-03** An invite is a link (`https://<app>/join/<code>`). The admin can share it with one tap through the **native share sheet** (WhatsApp, Messages, Mail, …). Where no share sheet exists, a copy button is offered.
  - The prepared message, in the admin's language, has two steps: (1) accept the Tailscale share, (2) tap the link to register.
- **ACC-04** The invite code is consumed only when the registration form is **submitted**. Opening the link, or a chat app generating a link preview, must not use it up.
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
- **ACC-07** After registering, or after using a reset link, the user is logged in immediately.
- **ACC-08** Users stay logged in as long as they use the app at least once every **90 days** (sliding expiry).
- **ACC-09** Users can:
  - see their active sessions;
  - log out the current device;
  - log out **all devices**;
  - change their password (which logs out all other devices).
- **ACC-10** Forgotten password: an admin creates a single-use **reset link**, valid 24 h, and shares it the same way as an invite. Using it sets a new password and ends all of that user's sessions.
- **ACC-11** Wrong login attempts slow down further attempts for that username and client (increasing delay). No account is ever permanently locked.
- **ACC-12** The **first admin** is created with a command on the Pi (`mealmate create-admin`), which asks for the username and password interactively. If the last admin is locked out, `mealmate reset-link <username>` prints a reset link.
- **ACC-13** Users can change their display name, language and privacy settings.

### 4.2 Couples (CPL)

- **CPL-01** A user can send another user a **couple request**. The other user can accept or decline it, and the sender can cancel it.
  - A user can be in at most one couple.
  - A user can have at most one outgoing pending request.
  - Accepting cancels all other pending requests that involve either user.
- **CPL-02** Each shopping list has a **"shared with partner"** switch. It defaults to **on** for new lists while the owner is in a couple, and only the owner can change it.
- **CPL-03** On a shared list, the partner can do everything the owner can except delete it and change the share switch:
  - rename it;
  - add or remove meals and change servings;
  - add extra items;
  - check items off;
  - start and finish shopping.
- **CPL-04** Privacy settings (VIS-02) **never** hide anything from the user's own partner. Partners always see each other's meals and shared lists.
- **CPL-05** Either partner can end the couple at any time. Afterwards, every list stays with its **creator** (including history), and the other person loses access.
- **CPL-06** Meals always stay separate per user, also within a couple.

### 4.3 Privacy and visibility (VIS)

- **VIS-01** By default everything a user creates is visible to all users of the instance.
  - Ingredients and products are always shared.
  - Meals and lists belong to their owner.
- **VIS-02** Each user has two privacy switches, **meals public** and **lists public**. Both default to on (public).
  - When a switch is off, other users (except the partner, CPL-04) cannot see those meals or lists.
  - While the meals switch is off, the user's name disappears from other users' **user filter chips** (MEAL-10).
- **VIS-03** Other people's public lists are **read-only**. They offer **"Copy to my lists"**, which creates a new draft with the same meals, servings and extra items.
- **VIS-04** Other people's visible meals can be viewed, added to one's own lists (LIST-03) and copied (MEAL-08). Only the owner can edit or delete a meal.
- **VIS-05** Photos are only served to users who are allowed to see the meal. URLs must not be guessable, and a URL without authorization must not work.

### 4.4 Reference data: categories, units, cuisines, tags (REF)

- **REF-01** **Categories** are seeded once, globally, with translation keys, in a default German-supermarket walking order. The seed list is in the [appendix](#appendix-a--seed-data).
  - Admins can **reorder** categories to match the store.
  - Adding or renaming categories needs a new app version.
  - `Other / Sonstiges` always exists.
- **REF-02** **Units:** `g`, `kg`, `ml`, `l`, `piece`, `tbsp`, `tsp`. They are fixed and shown translated (`Stk.`/`pcs`, `EL`/`tbsp`, `TL`/`tsp`).
  - Conversions: 1 kg = 1000 g, 1 l = 1000 ml, 1 tbsp = 15 ml, 1 tsp = 5 ml.
- **REF-03** **Cuisines:** a seeded, translated pick-list. Any user can add further cuisines as plain text. A meal has 0 or 1 cuisine.
- **REF-04** **Tags:** free text, 0 or more per meal, from one shared pool with autocomplete. Unique ignoring case and umlauts. Not translated.

### 4.5 Ingredients and products (ING)

- **ING-01** Ingredients are **shared by all users**. Any user can create one and **edit** any one, like a household wiki. The app records and shows "created by" and "last changed by".
- **ING-02** An ingredient has:
  - a **name** (one name, stored as typed, not translated; unique ignoring case and umlauts);
  - a **category** (required, default *Other*);
  - a **base unit** (`g` or `ml`, required, default `g`);
  - an optional **weight of one piece** in g (e.g. egg = 60 g);
  - an optional **density** in g per ml;
  - optional manual nutrition values (NUT-02).
- **ING-03** Search ignores case, umlauts and accents: `apfel`, `Äpfel` and `aepfel` all find "Äpfel". When a user creates an ingredient, a "similar ingredient already exists" hint is shown.
- **ING-04** An ingredient has 0 or more linked **products** (barcodes). Each product is linked to exactly one ingredient, and its nutrition basis (per 100 g or per 100 ml) must match the ingredient's base unit.
- **ING-05** Only admins can **delete** an ingredient, and only while nothing references it. Otherwise admins can **merge** duplicate ingredients ("merge A into B"): every meal, list and product reference is moved to B, and A is deleted.
- **ING-06** Ingredients created by a user who is later deleted stay, shown as created by "deleted user".

### 4.6 Nutrition (NUT)

- **NUT-01** Tracked nutrients: **kcal, protein, carbohydrates, sugar, fat**, per 100 g or 100 ml. Adding a nutrient later must only require adding it to one registry in code, one database migration and translations (see plan).
- **NUT-02** An ingredient's value for each nutrient, decided field by field:
  1. the **manual value**, if one is set;
  2. else the **average over its linked products** that have a value for that nutrient, with every product weighted equally;
  3. else **unknown**. Unknown is never treated as 0.

  When a manual value exists, the product average is shown next to it as a hint.
- **NUT-03** A meal's nutrition is the sum over its ingredients (amount converted to the base unit × value per 100). It is shown **per meal** and **per serving** (total ÷ `servings`).
- **NUT-04** If any ingredient value is unknown or an amount can't be converted, the total shows what can be calculated plus an **"incomplete"** marker. The marker names the missing ingredients or fields.
- **NUT-05** Conversions needed for nutrition:
  - `piece` uses the ingredient's piece weight;
  - g↔ml uses its density;
  - spoons of a g-based ingredient without density are counted as 1 g/ml and marked **"estimate"**.
- **NUT-06** Nutrition is computed when requested, not stored, so ingredient changes show up everywhere immediately.

### 4.7 Barcode scanning and Open Food Facts (BAR)

- **BAR-01** A **scan button** is available in the ingredient picker of the meal form and on the Ingredients tab. It uses the phone camera (EAN-13, EAN-8, UPC-A, UPC-E). The barcode can also be typed in by hand as a fallback.
- **BAR-02** Lookup order: own database first, then OFF. A known barcode goes straight to its ingredient.
- **BAR-03** For an unknown barcode, the app shows the OFF product (name in the user's language if available, brand, quantity, nutrition), or "not found – enter values yourself". It then asks **"Which ingredient is this?"**, with name-matched suggestions and "Create new ingredient" (name prefilled, category guessed or chosen). The user can correct values before saving.
- **BAR-04** Values the user changed or typed are marked as **user-edited per field** and are never overwritten automatically.
- **BAR-05** Cached OFF data is refreshed when older than **30 days** (configurable):
  - in the background when the product is scanned or opened;
  - by a nightly job.
- **BAR-06** When a refresh returns new values:
  - fields that were not user-edited update silently;
  - for user-edited fields, the app shows a hint: "Open Food Facts has newer values: kcal 165 → 158 [Apply] [Ignore]".
- **BAR-07** When OFF is unreachable, or the product was removed there, the cached values stay and the next scheduled refresh tries again.
- **BAR-08** OFF usage rules:
  - a descriptive User-Agent (`MealMate/<version> (<contact>)`);
  - at most 10 product requests per minute from the server (OFF allows 15);
  - no search-as-you-type against OFF.
- **BAR-09** Attribution "Nutrition data: Open Food Facts (ODbL)" with a link is shown wherever OFF data is displayed and on the About page. Product images from OFF are not stored or shown in v2.0.

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
- **MEAL-03** In the meal form, a missing ingredient can be **created inline** with just a name and category. The scan button is available there too.
- **MEAL-04** **Photo:**
  - taken with the camera or picked from the library;
  - shrunk on the phone before upload (about 1600 px);
  - on the server it is re-encoded, so all metadata including **GPS** is removed, and stored with a thumbnail under a random name;
  - JPEG, PNG and WebP up to 10 MB are accepted.
- **MEAL-05** **Source link:** any `http(s)` URL (other schemes are rejected). It is shown as a prominent button that opens the link in Safari / a new tab. There is no link preview.
- **MEAL-06** Meal detail shows the photo, nutrition per meal and per serving (NUT-03/04), ingredients, instructions, source button, owner, and "based on *X* by *Y*" for copies.
- **MEAL-07** Only the **owner** can edit or delete a meal. Deleting removes it from all **draft** lists. Lists in *shopping* or *done* keep their frozen copy (LIST-11).
- **MEAL-08** **Copy** (one tap, on any meal visible to the user) creates an independent meal owned by the copier. It includes ingredients, amounts, instructions, cuisine, tags, source link and its own copy of the photo, and it remembers the original ("based on X by Y"). The reference disappears when the original is deleted or becomes invisible.
- **MEAL-09** The meal list supports search (name, tag, cuisine), filters by cuisine and tag, and sorts A–Z. The list-building picker shows "recently used" meals first.
- **MEAL-10** **User filter chips** show one chip per user whose meals are visible, including oneself. Each chip toggles that user's meals on or off. The chip selection is saved per user, on the server, so it follows them across devices.

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
- **LIST-08** Tapping a line shows which meals and extra items it comes from.
- **LIST-09** Every change is saved to the server immediately. A draft can be continued on another device, even after closing the app or restarting the phone. Offline behaviour is covered in SYNC.
- **LIST-10** **List states:**

  | State | Meaning |
  |---|---|
  | `draft` | Being planned. Lines are computed live from the current meals. |
  | `shopping` | "Start shopping" pressed. Meal ingredients are frozen (LIST-11) and items are checked off. |
  | `done` | "Finish shopping" pressed. Read-only. Appears in history. |

- **LIST-11** **Freezing:** on "Start shopping", each meal's current ingredients are copied into the list. From then on, edits to or deletion of the meal no longer change this list or its history. A meal added while shopping is frozen at the moment it's added.
- **LIST-12** **Editing while shopping** (online only): add or remove meals, change servings, add or remove extra items. This lets a partner at home change the list while the other person is in the store.
  - A new line appears unchecked and marked "new".
  - If a **checked** line needs more afterwards, it becomes **unchecked** and shows the difference (e.g. "+300 g").
  - A checked line that needs less stays checked.
- **LIST-13** **Delete:** the owner can delete a list in any state, after a confirmation.
- **LIST-14** **Reminder:** the last row of every list is a random, friendly reminder, e.g. "Nichts vergessen? Klopapier? Salz?" / "Didn't forget anything? Toilet paper? Salt?".
  - It comes from a pool of about 10 per language, kept in the translation files.
  - It stays the same for a given list.
  - The same reminder appears in the finish dialog (SHOP-04).

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
- **SHOP-05** **History:** done lists, grouped by the week they were **finished**, with the subtitle "bought on 26.09.".
  - Checked lines count as bought; unchecked lines are shown greyed.
  - Shared lists appear in both partners' history while the couple exists (see CPL-05 for what happens after).
- **SHOP-06** A done list offers **"Shop again"**, which creates a new draft with the same meals (current versions), servings and extra items, all unchecked. It also offers **"Reopen"**, which moves it back to *shopping*, in case *Finish* was tapped by mistake.

### 4.12 Offline use and sync (SYNC)

- **SYNC-01** MealMate is installable as a **Home Screen web app** (PWA). After the first login a one-time hint shows how to "Add to Home Screen". Reliable offline use is only guaranteed in the Home Screen app.
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
- **SYNC-07** **Sync status indicator**, one of:
  - "Saved";
  - "Offline – *N* changes waiting";
  - "Can't reach MealMate – no signal or Tailscale off?".

  Actions not yet delivered look slightly faded. A banner appears if changes have been waiting for more than one hour.
- **SYNC-08** **Live updates:** while a list is on screen, the app checks for changes about every **5 seconds** and immediately when it returns to the foreground. Pull-to-refresh is available. There are no push notifications in v2.0.
- **SYNC-09** **App loads offline:** the app shell (HTML, JS, CSS, icons, translations) is cached so the app opens without a connection. Screens other than cached lists show a friendly offline message.

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
  - promoting and demoting admins (at least one admin must always remain);
  - deactivating, reactivating and deleting users;
  - reordering categories;
  - merging and deleting ingredients;
  - system info: app version, last successful backup, free disk space.
- **ADM-02** **Deactivating** a user blocks login immediately and ends all their sessions. Their data stays, and their name is shown with "(deactivated)". Deactivation can be undone.
- **ADM-03** **Deleting** a user removes:
  - their meals and photos;
  - their lists that are not shared with a partner, including history;
  - their pending couple requests;
  - any unused invites or reset links issued for them.

  It also ends their couple. Their shared lists move to the partner. Ingredients and products they created stay ("deleted user"). Copies other people made of their meals stay. The last admin can't be deleted.
- **ADM-04** Admins **cannot** see other users' private meals or lists, and cannot log in as another user.

### 4.16 App shell and navigation (UI)

- **UI-01** Mobile-first layout for iPhone, one-handed use. There is a bottom tab bar with **Lists**, **Meals**, **Ingredients** and **Me**.
- **UI-02** The app opens on **Lists**:
  - a list in *shopping* state appears at the top as a large "Continue shopping" card;
  - then drafts, most recently edited first, including the partner's shared lists;
  - then an entry to **History**;
  - then **Others' lists**: other users' public lists, read-only, with the user filter chips.
- **UI-03** Every empty screen shows one friendly sentence and one main action, e.g. "No meals yet – create your first meal".
- **UI-04** Dark mode follows the iPhone setting automatically.
- **UI-05** Branding: name **MealMate**, a green accent colour (from the v1 `#4CAF50` family), and a simple basket icon for the Home Screen and favicon. All colours are defined once as design tokens so the design can be re-skinned easily.
- **UI-06** The *Me* tab shows the version and a **"Source code (AGPL-3.0)"** link to the exact source revision being run (LIC-02). It also contains the OFF attribution (BAR-09).

## 5. Non-functional requirements

### 5.1 Platform and deployment (PLT)

- **PLT-01** **Target hardware:** Raspberry Pi 3 Model B v1.2 (4 × Cortex-A53, 1 GB RAM, 100 Mbit Ethernet), microSD card of **16 GB or more** (32 GB preferred), official 2.5 A power supply.
- **PLT-02** **OS:** Raspberry Pi OS Lite **64-bit**, headless, hostname `mealmate`, SSH with key only (no password login), automatic security updates. It is set up to write as little as possible to the SD card (logs in RAM, capped Docker logs, `noatime`).
- **PLT-03** **Delivery:** the app runs as **one Docker container** from a prebuilt `linux/arm64` image on `ghcr.io`, started with Docker Compose. Nothing is built on the Pi.
- **PLT-04** **Remote access** only via **Tailscale**:
  - Tailscale runs on the Pi's operating system, not in Docker.
  - Every user installs the Tailscale app and leaves it on (VPN On Demand keeps it connected).
  - The Pi is **shared** with each user (node sharing), so users can reach only the Pi, and a tailnet policy limits them to HTTPS.
  - No router ports are opened.
- **PLT-05** **HTTPS:**
  - HTTPS is provided by `tailscale serve`, with a browser-trusted certificate for `https://mealmate.<tailnet>.ts.net`.
  - This is the **only** address; there is no second LAN address, because each address would mean a separate login and separate offline data.
  - The app container listens on `127.0.0.1` only.
- **PLT-06** Setting up a new SD card (initial install, card swap, disaster recovery) is **one documented, scripted procedure**: flash with Raspberry Pi Imager → run the setup script → optionally restore a backup. It takes about 30 minutes and is tested before go-live (OPS-07).

### 5.2 Security and privacy (SEC)

- **SEC-01** **The repository is public.**
  - No secret, key, certificate, password or personal data may ever be committed.
  - CI runs a secret scanner.
  - GitHub push protection is enabled.
  - The v1 self-signed key (`certs/key.pem`, public in git history) is considered compromised and is never reused.
- **SEC-02** Secrets live only in `/srv/mealmate/.env` on the Pi, readable only by the owner:
  - `SECRET_KEY`, generated randomly by the setup script;
  - the healthchecks.io ping URLs.

  **No secret has a default value in code.** The app refuses to start without a `SECRET_KEY`.
- **SEC-03** **Authentication:**
  - short-lived access tokens (15 min, held in memory);
  - a rotating refresh token in an `HttpOnly; Secure; SameSite=Strict` cookie, stored hashed on the server;
  - sessions can be revoked on the server;
  - passwords hashed with bcrypt.
- **SEC-04** **Authorization** is checked in the backend for every request and every object (owner / partner / public / admin). It is covered by API tests, including "user A can't read or change user B's private data".
- **SEC-05** **Rate limiting:**
  - login (per username + client);
  - registration and reset (per client);
  - uploads (per user);
  - barcode lookups (per user);
  - a general per-user request limit.

  The client address is taken from `X-Forwarded-For`, and that header is trusted only from `127.0.0.1` (tailscale serve).
- **SEC-06** **Security headers:**
  - a strict Content-Security-Policy (no inline scripts; `wasm-unsafe-eval` only if the barcode decoder needs it);
  - `X-Content-Type-Options`;
  - `Referrer-Policy: no-referrer`;
  - `frame-ancestors 'none'`.

  Outgoing source links use `rel="noopener noreferrer"`.
- **SEC-07** **Uploads:** the real file type is checked, pixel count and file size are limited, the image is always re-encoded (which strips metadata) and stored under a random name outside any web root.
- **SEC-08** **No personal data beyond what's needed:** no email addresses, and no tracking or analytics. No third-party requests from the browser. OFF is contacted only by the server.
- **SEC-09** The container runs as a **non-root** user with a read-only root filesystem, except for the data volume. It contains no dev tools.
- **SEC-10** Invite codes, reset codes and refresh tokens are long random values (≥ 128 bit) and are stored **hashed**.
- **SEC-11** Dependencies are kept current (Dependabot weekly, grouped). CI fails on known high or critical vulnerabilities in runtime dependencies.

### 5.3 Backups, monitoring and updates (OPS)

- **OPS-01** **Backups every 6 hours** on the Pi. Each backup contains:
  - a consistent SQLite snapshot (made with SQLite's backup API, never by copying the raw file), integrity-checked;
  - the photos (stored incrementally: unchanged photos are hard-linked, not copied again);
  - `.env`;
  - the Pi's Tailscale identity (node state), so a restore keeps the same address and shares;
  - a manifest with app version, time and checksums.
- **OPS-02** **Retention** on the Pi, at most about 21 backups:
  - the 4 most recent (last 24 h);
  - plus the newest per day for 7 days;
  - plus the newest per week for 4 weeks;
  - plus the newest per month for 6 months.
- **OPS-03** **Off-Pi copy:** the owner's **Mac pulls** new backups automatically over Tailscale.
  - It runs every hour while the Mac is awake, via `launchd`, and catches up after sleep.
  - It uses a dedicated SSH key that is restricted on the Pi to **read-only** access to the backup folder.
  - The Mac applies its own retention and **never mirrors deletions** from the Pi, so a compromised Pi cannot delete the Mac's copies.
  - One command installs it on the Mac.
- **OPS-04** **Alerts** come from a free external dead-man's-switch service (healthchecks.io), by email; push via ntfy or Telegram is optional. Checks:

  | Check | Pinged by | Alert when |
  |---|---|---|
  | `heartbeat` | Pi, every 5 min, only if the app's health endpoint answers OK | silent for 15 min: Pi, Docker, app or internet down |
  | `backup` | Pi, after each successful backup | silent for 8 h |
  | `mac-pull` | Mac, after each successful pull | silent for 3 days |
  | `update` | Pi, after each nightly update run | a failure or rollback, or silent for 2 days |
  | `disk` | Pi, every hour | free space below 20 % |

- **OPS-05** **Updates:**
  - The Pi follows the **version line** of its release, e.g. image tag `2.0`: bug-fix releases (`2.0.1`, `2.0.2`) are installed automatically at night.
  - Moving to a new feature version (`2.1`) is a deliberate one-line change.
  - Before an update: a backup. After it: a health check. If that fails: **automatic rollback** (previous image plus pre-update database) and an alert.
  - A manual `update.sh` exists too.
- **OPS-06** Database migrations run automatically at container start. The entrypoint first saves a pre-migration snapshot whenever migrations are pending.
- **OPS-07** **Restore:**
  - `restore.sh` restores a chosen backup onto a freshly set-up card: database, photos, `.env` and Tailscale identity.
  - The full procedure is rehearsed on a spare SD card before go-live.
  - A monthly automatic test restore of the latest backup into a temporary file is integrity-checked.
- **OPS-08** A manual backup can be started with one command (and from the admin page) before planned maintenance, such as an SD card swap.
- **OPS-09** The old and the new SD card must never run at the same time. Both would claim the same Tailscale identity, so the runbook warns about this.

### 5.4 Performance and resources (PERF)

- **PERF-01** The container uses **< 200 MB RAM** when idle and < 300 MB under normal use on the Pi 3. It runs one app process, and background jobs run as short-lived commands.
- **PERF-02** On the Pi 3, API responses for a list with 20 meals and 150 lines take < 300 ms (p95). Opening a cached list works instantly, even offline.
- **PERF-03** Initial JavaScript is < 300 KB gzipped. The barcode decoder and other heavy parts are loaded only when needed.
- **PERF-04** The container is healthy within 60 s after start on the Pi 3, including migrations.
- **PERF-05** Password hashing takes about 250–500 ms on the Pi 3 (the bcrypt cost factor is tuned for this).

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
- **MNT-03** A frontend developer can run the full stack on a laptop with one command, with hot reload and demo data (`seed-demo`), without the Pi.
- **MNT-04** Conventions are documented in `CONTRIBUTING.md` and `frontend/README.md`:
  - all strings go through i18n keys;
  - API calls only through `src/api/`;
  - interactive elements get accessible names and `data-testid`;
  - UI building blocks live in `src/components/ui/`.
- **MNT-05** UI building blocks (dialogs, sheets, dropdowns, toasts, chips) come from **shadcn/ui**, whose source is copied into the repo, so it can be restyled freely without lock-in. Styling uses Tailwind design tokens.
- **MNT-06** Adding a nutrient, a unit conversion, a category, a cuisine or a language follows a documented checklist.

### 5.7 Testing and quality gates (QA)

- **QA-01** **Backend:**
  - `pytest` unit and API tests;
  - **≥ 85 % line coverage** enforced in CI;
  - unit conversion, aggregation, servings scaling, rounding and nutrition aim for ~100 %, using table-driven tests plus property-based tests (Hypothesis).
- **QA-02** **Migrations:** every Alembic migration upgrades and downgrades cleanly from an empty database, and the models match the latest migration (no pending autogenerate diff).
- **QA-03** **Frontend:** Vitest for logic (API client, number parsing and formatting, offline queue, export text, i18n completeness).
- **QA-04** **End-to-end** tests in **Python (pytest-playwright)** against the built container, in **Chromium and WebKit** with an iPhone viewport, on every pull request. Covered flows:
  1. register via invite;
  2. login, refresh and logout;
  3. create an ingredient from an injected barcode, with OFF mocked;
  4. create a meal and check its nutrition;
  5. copy another user's meal;
  6. build a list from meals with servings plus extra items, and check aggregation and category order;
  7. check items off offline and see them sync after reconnecting;
  8. export through a stubbed share sheet;
  9. the privacy toggle hides a user;
  10. switch language between German and English;
  11. couple sharing: the partner sees and checks off a shared list.
- **QA-05** E2E tests find elements by role, accessible name or `data-testid`, never by CSS classes, so the frontend can be restyled without breaking tests.
- **QA-06** Before every release tag, a **manual checklist on a real iPhone** (about 10 minutes): camera scan, share to Notes, offline check-off and sync, Home Screen install, dark mode.
- **QA-07** **Linting and formatting** are enforced in CI:
  - backend: ruff (lint and format) and mypy;
  - frontend: eslint, prettier and `tsc`.

### 5.8 Licensing and repository (LIC)

- **LIC-01** The project is licensed under **AGPL-3.0-only** (changed from GPL-3.0). All code so far is by the owner, so no consent from others is needed.
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
| D-06 | Generic ingredient + linked barcode products, with nutrition = per-field average | meals stay brand-independent; brands only matter when scanning |
| D-07 | Servings = "the recipe makes *N*" (default 1); lists scale by the chosen servings | covers both "per serving" and "whole recipe" |
| D-08 | Lists freeze meal ingredients at "Start shopping" | history stays true; check-off has stable lines |
| D-09 | No households now | single persons and couples are enough; can be added with a migration later |
| D-10 | Offline limited to check-off, free-text items and finishing | everything else needs server-side calculation (AGG-01) |
| D-11 | 5-second polling instead of a live connection | nearly free on a Pi 3; no reconnect handling on locked iPhones |
| D-12 | Mac pulls backups; healthchecks.io dead-man's switch for alerts | no cloud storage needed; a dead Pi can't send its own alert |
| D-13 | Pi follows the version line (`2.0`) with automatic rollback | hotfixes arrive automatically; migrations of feature versions are applied deliberately |
| D-14 | E2E tests in Python | owner's language; the frontend developer only has to keep the test IDs stable |
| D-15 | AGPL-3.0 | hosted modified copies must share their source |
| D-16 | Open Food Facts API v3, ≤ 10 requests/min | v2 was deprecated in June 2026; OFF allows 15 product reads/min per IP |

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
