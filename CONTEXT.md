# MealMate

A self-hosted app for one household of 1–10 users that turns saved meals into a category-sorted shopping list for fast supermarket trips, including checking items off in the store.

## Language

### People

**User**:
Someone with an account on this MealMate instance.
_Avoid_: account, member

**Admin**:
A user with the admin role, who manages users, invites and the shared reference data.
_Avoid_: moderator, superuser

**Couple**:
Two users who have agreed to share shopping lists. A user is in at most one couple.
_Avoid_: household, pair, group

**Partner**:
The other user in one's couple.
_Avoid_: spouse, co-owner

### Food

**Ingredient**:
A food item shared by all users: either something generic typed by hand ("Zwiebel") or a specific product with a brand and a barcode, usually from OFF ("Milch (Weihenstephan)"). It has a category, a base unit (g or ml) and its own nutrition values per 100 g/ml. There is only this one kind; two brands of the same thing are two ingredients.
_Avoid_: product, food, article

**Brand**:
The maker's name on an ingredient that is a specific product (e.g. "Weihenstephan"). It is optional and always shown after the ingredient's name.
_Avoid_: manufacturer, label

**Barcode**:
The EAN or UPC number printed on a package. An ingredient has at most one, and no two ingredients share one.
_Avoid_: EAN, code, product

**Category**:
The supermarket section an ingredient belongs to (e.g. "Obst & Gemüse"). Admins put categories in the store's walking order.
_Avoid_: aisle, section, department

**Meal**:
A recipe owned by one user: ingredients with amounts, instructions, photo, source link, and "makes N servings".
_Avoid_: recipe, dish

**Serving**:
One portion. A meal's servings value is how many portions its ingredient amounts make.
_Avoid_: portion

**Cuisine**:
The cooking style of a meal (e.g. "Italienisch"), from a translated pick-list that users can extend. A meal has at most one.
_Avoid_: kitchen, style

**Tag**:
A free-text label on a meal (e.g. "schnell"), from one pool shared by all users. A meal can have several.
_Avoid_: label, keyword, category (categories belong to ingredients)

**OFF**:
Open Food Facts, the open database of packaged foods in which barcodes and names are looked up.

### Shopping lists

**Shopping list**:
A list owned by one user, built from meals (each with a chosen number of servings) plus extra items.
_Avoid_: cart, list (on its own, where it could mean any list)

**Owner**:
The user who created a shopping list or meal. Ownership never moves to another user; copying creates a new item with a new owner.
_Avoid_: creator, author

**Shared list**:
A shopping list whose owner has switched on "shared with partner", so the partner can edit it as well.
_Avoid_: joint list, common list

**Read-only list**:
Another user's shopping list that one can see but not edit: the public list of someone who isn't one's partner, or the partner's list that isn't shared. It can be copied into a new draft. A done list is not a read-only list just because it can no longer change.
_Avoid_: others' list, foreign list

**User filter**:
A user's saved choice of whose meals, and separately whose shopping lists, they see, including their own and their partner's. It follows them across devices.
_Avoid_: person filter, user chips, meal chips, list chips

**Draft**:
A shopping list that is still being planned. Its lines follow the current meals.
_Avoid_: planned list, open list

**Shopping** (state):
A shopping list that is being shopped in the store. Its meals' ingredients are frozen and its lines are checked off.
_Avoid_: active list, in progress

**Done list**:
A shopping list whose shopping was finished. It is read-only and kept as the owner's history.
_Avoid_: archived list, completed list, history entry

**Line**:
One row on a shopping list after aggregation (e.g. "Zwiebeln 500 g"), merging the same ingredient from all meals and extra items. Two brands of the same thing are two ingredients, so they make two lines.
_Avoid_: entry, position, row

**Extra item**:
Something added to a shopping list by hand, either linked to an ingredient ("1 l Milch") or free text ("Geburtstagskerzen").
_Avoid_: manual item, custom item

**Frozen meal**:
A meal on a shopping list whose ingredients were copied into the list when shopping started, so later changes to the meal no longer affect that list.
_Avoid_: snapshot, locked meal

**Detached meal**:
A meal on a draft that was deleted or stopped being visible to the list's owner. Its ingredients were frozen into the list and it is marked "no longer available".
_Avoid_: orphaned meal, removed meal
