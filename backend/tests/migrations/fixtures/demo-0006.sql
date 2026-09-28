-- The demo database of `mealmate seed-demo` at revision 0006 (before ingredients and
-- products were merged), dumped with sqlite3's iterdump. Password hashes and the invite
-- code are replaced by placeholders. Used by tests/migrations to migrate real 0006 data.
BEGIN TRANSACTION;
CREATE TABLE admin_events (
	actor_id VARCHAR(36),
	action VARCHAR(40) NOT NULL,
	target_user_id VARCHAR(36),
	details JSON NOT NULL,
	created_at DATETIME NOT NULL,
	id VARCHAR(36) NOT NULL,
	CONSTRAINT pk_admin_events PRIMARY KEY (id),
	CONSTRAINT fk_admin_events_actor_id_users FOREIGN KEY(actor_id) REFERENCES users (id) ON DELETE SET NULL,
	CONSTRAINT fk_admin_events_target_user_id_users FOREIGN KEY(target_user_id) REFERENCES users (id) ON DELETE SET NULL
);
INSERT INTO "admin_events" VALUES('01a0e7f4-9942-7185-9914-b342d32c4fdb','invite.create',NULL,'{"invite_id": "01a0e7f4-9964-7345-b2a6-92be9607ef2c"}','2026-09-28 12:19:20.444234','01a0e7f4-996d-702e-9b21-773bcd118044');
CREATE TABLE alembic_version (
	version_num VARCHAR(32) NOT NULL,
	CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
INSERT INTO "alembic_version" VALUES('0006');
CREATE TABLE app_meta (
	"key" VARCHAR(64) NOT NULL,
	value TEXT NOT NULL,
	CONSTRAINT pk_app_meta PRIMARY KEY ("key")
);
CREATE TABLE categories (
	"key" VARCHAR(40) NOT NULL,
	sort_order INTEGER NOT NULL,
	id VARCHAR(36) NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	CONSTRAINT pk_categories PRIMARY KEY (id),
	CONSTRAINT uq_categories_key UNIQUE ("key")
);
INSERT INTO "categories" VALUES('fruit_vegetables',0,'01a0e7f4-8a49-7790-a800-e83c059e51cc','2026-09-28 12:19:18.217576','2026-09-28 12:19:18.217576');
INSERT INTO "categories" VALUES('bread_bakery',1,'01a0e7f4-8a49-7790-a800-e83d1da5a177','2026-09-28 12:19:18.217576','2026-09-28 12:19:18.217576');
INSERT INTO "categories" VALUES('dairy_eggs',2,'01a0e7f4-8a49-7790-a800-e83e5672f26e','2026-09-28 12:19:18.217576','2026-09-28 12:19:18.217576');
INSERT INTO "categories" VALUES('cheese',3,'01a0e7f4-8a49-7790-a800-e83ffc117fc7','2026-09-28 12:19:18.217576','2026-09-28 12:19:18.217576');
INSERT INTO "categories" VALUES('meat_fish',4,'01a0e7f4-8a49-7790-a800-e840e6092581','2026-09-28 12:19:18.217576','2026-09-28 12:19:18.217576');
INSERT INTO "categories" VALUES('sausage_deli',5,'01a0e7f4-8a49-7790-a800-e8412257111f','2026-09-28 12:19:18.217576','2026-09-28 12:19:18.217576');
INSERT INTO "categories" VALUES('plant_based',6,'01a0e7f4-8a49-7790-a800-e842c900c62f','2026-09-28 12:19:18.217576','2026-09-28 12:19:18.217576');
INSERT INTO "categories" VALUES('pasta_rice_grains',7,'01a0e7f4-8a49-7790-a800-e84364691afd','2026-09-28 12:19:18.217576','2026-09-28 12:19:18.217576');
INSERT INTO "categories" VALUES('canned_jars',8,'01a0e7f4-8a49-7790-a800-e844336f42bf','2026-09-28 12:19:18.217576','2026-09-28 12:19:18.217576');
INSERT INTO "categories" VALUES('sauces_spices_oils',9,'01a0e7f4-8a49-7790-a800-e8451ad739d5','2026-09-28 12:19:18.217576','2026-09-28 12:19:18.217576');
INSERT INTO "categories" VALUES('baking',10,'01a0e7f4-8a49-7790-a800-e8467e1f0b87','2026-09-28 12:19:18.217576','2026-09-28 12:19:18.217576');
INSERT INTO "categories" VALUES('breakfast_spreads',11,'01a0e7f4-8a49-7790-a800-e84720d7b97a','2026-09-28 12:19:18.217576','2026-09-28 12:19:18.217576');
INSERT INTO "categories" VALUES('snacks_sweets',12,'01a0e7f4-8a49-7790-a800-e8484c3f43e5','2026-09-28 12:19:18.217576','2026-09-28 12:19:18.217576');
INSERT INTO "categories" VALUES('frozen',13,'01a0e7f4-8a49-7790-a800-e8491be9655b','2026-09-28 12:19:18.217576','2026-09-28 12:19:18.217576');
INSERT INTO "categories" VALUES('drinks',14,'01a0e7f4-8a49-7790-a800-e84a287fa151','2026-09-28 12:19:18.217576','2026-09-28 12:19:18.217576');
INSERT INTO "categories" VALUES('household_hygiene',15,'01a0e7f4-8a49-7790-a800-e84b20e1487a','2026-09-28 12:19:18.217576','2026-09-28 12:19:18.217576');
INSERT INTO "categories" VALUES('other',16,'01a0e7f4-8a49-7790-a800-e84c01f4b0e9','2026-09-28 12:19:18.217576','2026-09-28 12:19:18.217576');
CREATE TABLE couple_members (
	user_id VARCHAR(36) NOT NULL,
	couple_id VARCHAR(36) NOT NULL,
	CONSTRAINT pk_couple_members PRIMARY KEY (user_id),
	CONSTRAINT fk_couple_members_couple_id_couples FOREIGN KEY(couple_id) REFERENCES couples (id) ON DELETE CASCADE,
	CONSTRAINT fk_couple_members_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
INSERT INTO "couple_members" VALUES('01a0e7f4-994b-76eb-9ac0-d721e855fb70','01a0e7f4-995b-7231-87d9-4076436effa6');
INSERT INTO "couple_members" VALUES('01a0e7f4-9952-7024-a21f-c60df788c992','01a0e7f4-995b-7231-87d9-4076436effa6');
CREATE TABLE couples (
	requester_id VARCHAR(36) NOT NULL,
	addressee_id VARCHAR(36) NOT NULL,
	status VARCHAR(10) NOT NULL,
	accepted_at DATETIME,
	id VARCHAR(36) NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	CONSTRAINT pk_couples PRIMARY KEY (id),
	CONSTRAINT ck_couples_status CHECK (status IN ('pending', 'accepted')),
	CONSTRAINT fk_couples_addressee_id_users FOREIGN KEY(addressee_id) REFERENCES users (id) ON DELETE CASCADE,
	CONSTRAINT fk_couples_requester_id_users FOREIGN KEY(requester_id) REFERENCES users (id) ON DELETE CASCADE
);
INSERT INTO "couples" VALUES('01a0e7f4-994b-76eb-9ac0-d721e855fb70','01a0e7f4-9952-7024-a21f-c60df788c992','accepted','2026-09-28 12:19:20.444234','01a0e7f4-995b-7231-87d9-4076436effa6','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
CREATE TABLE cuisines (
	"key" VARCHAR(40),
	name VARCHAR(40),
	name_norm VARCHAR(160) NOT NULL,
	created_by VARCHAR(36),
	id VARCHAR(36) NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	CONSTRAINT pk_cuisines PRIMARY KEY (id),
	CONSTRAINT ck_cuisines_key_or_name CHECK ((key IS NULL) <> (name IS NULL)),
	CONSTRAINT fk_cuisines_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL,
	CONSTRAINT uq_cuisines_key UNIQUE ("key"),
	CONSTRAINT uq_cuisines_name_norm UNIQUE (name_norm)
);
INSERT INTO "cuisines" VALUES('german',NULL,'german',NULL,'01a0e7f4-8a4a-7284-a550-c301d98745ff','2026-09-28 12:19:18.217576','2026-09-28 12:19:18.217576');
INSERT INTO "cuisines" VALUES('italian',NULL,'italian',NULL,'01a0e7f4-8a4a-7284-a550-c30253c8d564','2026-09-28 12:19:18.217576','2026-09-28 12:19:18.217576');
INSERT INTO "cuisines" VALUES('french',NULL,'french',NULL,'01a0e7f4-8a4a-7284-a550-c303257911c3','2026-09-28 12:19:18.217576','2026-09-28 12:19:18.217576');
INSERT INTO "cuisines" VALUES('greek',NULL,'greek',NULL,'01a0e7f4-8a4a-7284-a550-c304f3affaf6','2026-09-28 12:19:18.217576','2026-09-28 12:19:18.217576');
INSERT INTO "cuisines" VALUES('turkish',NULL,'turkish',NULL,'01a0e7f4-8a4a-7284-a550-c305b98f03c5','2026-09-28 12:19:18.217576','2026-09-28 12:19:18.217576');
INSERT INTO "cuisines" VALUES('mediterranean',NULL,'mediterranean',NULL,'01a0e7f4-8a4a-7284-a550-c306cfcc717f','2026-09-28 12:19:18.217576','2026-09-28 12:19:18.217576');
INSERT INTO "cuisines" VALUES('american',NULL,'american',NULL,'01a0e7f4-8a4a-7284-a550-c3079572db3a','2026-09-28 12:19:18.217576','2026-09-28 12:19:18.217576');
INSERT INTO "cuisines" VALUES('mexican',NULL,'mexican',NULL,'01a0e7f4-8a4a-7284-a550-c308784229ee','2026-09-28 12:19:18.217576','2026-09-28 12:19:18.217576');
INSERT INTO "cuisines" VALUES('indian',NULL,'indian',NULL,'01a0e7f4-8a4a-7284-a550-c30973d28e98','2026-09-28 12:19:18.217576','2026-09-28 12:19:18.217576');
INSERT INTO "cuisines" VALUES('chinese',NULL,'chinese',NULL,'01a0e7f4-8a4a-7284-a550-c30a8709b408','2026-09-28 12:19:18.217576','2026-09-28 12:19:18.217576');
INSERT INTO "cuisines" VALUES('japanese',NULL,'japanese',NULL,'01a0e7f4-8a4a-7284-a550-c30b09003e70','2026-09-28 12:19:18.217576','2026-09-28 12:19:18.217576');
INSERT INTO "cuisines" VALUES('thai',NULL,'thai',NULL,'01a0e7f4-8a4a-7284-a550-c30ce14d02ee','2026-09-28 12:19:18.217576','2026-09-28 12:19:18.217576');
INSERT INTO "cuisines" VALUES('other',NULL,'other',NULL,'01a0e7f4-8a4a-7284-a550-c30da51cbe81','2026-09-28 12:19:18.217576','2026-09-28 12:19:18.217576');
CREATE TABLE ingredients (
	name VARCHAR(60) NOT NULL,
	name_norm VARCHAR(240) NOT NULL,
	category_id VARCHAR(36) NOT NULL,
	base_unit VARCHAR(2) NOT NULL,
	piece_weight_g FLOAT,
	density_g_per_ml FLOAT,
	kcal FLOAT,
	protein FLOAT,
	carbs FLOAT,
	sugar FLOAT,
	fat FLOAT,
	created_by VARCHAR(36),
	updated_by VARCHAR(36),
	id VARCHAR(36) NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	CONSTRAINT pk_ingredients PRIMARY KEY (id),
	CONSTRAINT ck_ingredients_base_unit CHECK (base_unit IN ('g', 'ml')),
	CONSTRAINT fk_ingredients_category_id_categories FOREIGN KEY(category_id) REFERENCES categories (id) ON DELETE RESTRICT,
	CONSTRAINT fk_ingredients_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL,
	CONSTRAINT fk_ingredients_updated_by_users FOREIGN KEY(updated_by) REFERENCES users (id) ON DELETE SET NULL,
	CONSTRAINT uq_ingredients_name_norm UNIQUE (name_norm)
);
INSERT INTO "ingredients" VALUES('Äpfel','aepfel','01a0e7f4-8a49-7790-a800-e83c059e51cc','g',180.0,NULL,52.0,0.3,11.4,10.4,0.2,'01a0e7f4-994b-76eb-9ac0-d721e855fb70','01a0e7f4-994b-76eb-9ac0-d721e855fb70','01a0e7f4-9979-721c-a25b-f58ead9f540a','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "ingredients" VALUES('Zwiebeln','zwiebeln','01a0e7f4-8a49-7790-a800-e83c059e51cc','g',150.0,NULL,40.0,1.1,9.3,4.2,0.1,'01a0e7f4-9952-7024-a21f-c60df788c992','01a0e7f4-9952-7024-a21f-c60df788c992','01a0e7f4-997c-72da-a684-55e358d4756f','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "ingredients" VALUES('Knoblauch','knoblauch','01a0e7f4-8a49-7790-a800-e83c059e51cc','g',5.0,NULL,NULL,NULL,NULL,NULL,NULL,'01a0e7f4-9957-73c7-9e4b-f263774bc144','01a0e7f4-9957-73c7-9e4b-f263774bc144','01a0e7f4-997e-742f-8983-096a5633adbe','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "ingredients" VALUES('Tomaten','tomaten','01a0e7f4-8a49-7790-a800-e83c059e51cc','g',100.0,NULL,18.0,0.9,3.9,2.6,0.2,'01a0e7f4-994b-76eb-9ac0-d721e855fb70','01a0e7f4-994b-76eb-9ac0-d721e855fb70','01a0e7f4-997f-71a4-b0c9-d01d591f9b00','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "ingredients" VALUES('Kartoffeln','kartoffeln','01a0e7f4-8a49-7790-a800-e83c059e51cc','g',150.0,NULL,77.0,2.0,17.0,0.8,0.1,'01a0e7f4-9952-7024-a21f-c60df788c992','01a0e7f4-9952-7024-a21f-c60df788c992','01a0e7f4-9981-773a-998d-d7caf32e5885','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "ingredients" VALUES('Karotten','karotten','01a0e7f4-8a49-7790-a800-e83c059e51cc','g',80.0,NULL,NULL,NULL,NULL,NULL,NULL,'01a0e7f4-9957-73c7-9e4b-f263774bc144','01a0e7f4-9957-73c7-9e4b-f263774bc144','01a0e7f4-9983-7750-a00d-c9a34a1781bb','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "ingredients" VALUES('Brot','brot','01a0e7f4-8a49-7790-a800-e83d1da5a177','g',NULL,NULL,245.0,8.5,45.0,3.0,1.6,'01a0e7f4-994b-76eb-9ac0-d721e855fb70','01a0e7f4-994b-76eb-9ac0-d721e855fb70','01a0e7f4-9984-7740-a316-18429919b60f','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "ingredients" VALUES('Milch','milch','01a0e7f4-8a49-7790-a800-e83e5672f26e','ml',NULL,1.03,64.0,3.4,4.8,4.8,3.5,'01a0e7f4-994b-76eb-9ac0-d721e855fb70','01a0e7f4-994b-76eb-9ac0-d721e855fb70','01a0e7f4-9986-779f-ad93-ea1b6428cf11','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "ingredients" VALUES('Eier','eier','01a0e7f4-8a49-7790-a800-e83e5672f26e','g',60.0,NULL,155.0,13.0,1.1,1.1,11.0,'01a0e7f4-9957-73c7-9e4b-f263774bc144','01a0e7f4-9957-73c7-9e4b-f263774bc144','01a0e7f4-9987-7723-89ce-9fd84073140c','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "ingredients" VALUES('Butter','butter','01a0e7f4-8a49-7790-a800-e83e5672f26e','g',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'01a0e7f4-9952-7024-a21f-c60df788c992','01a0e7f4-9952-7024-a21f-c60df788c992','01a0e7f4-9989-74dd-a236-202559a213b8','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "ingredients" VALUES('Joghurt','joghurt','01a0e7f4-8a49-7790-a800-e83e5672f26e','g',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'01a0e7f4-9952-7024-a21f-c60df788c992','01a0e7f4-9952-7024-a21f-c60df788c992','01a0e7f4-998a-77fd-bc50-c98b5f18fa2d','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "ingredients" VALUES('Gouda','gouda','01a0e7f4-8a49-7790-a800-e83ffc117fc7','g',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'01a0e7f4-994b-76eb-9ac0-d721e855fb70','01a0e7f4-994b-76eb-9ac0-d721e855fb70','01a0e7f4-998c-73ce-81fa-dd459eb0c6d2','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "ingredients" VALUES('Parmesan','parmesan','01a0e7f4-8a49-7790-a800-e83ffc117fc7','g',NULL,NULL,392.0,35.8,3.2,0.9,25.8,'01a0e7f4-9957-73c7-9e4b-f263774bc144','01a0e7f4-9957-73c7-9e4b-f263774bc144','01a0e7f4-998d-723c-bc7d-5b8d305b0d0d','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "ingredients" VALUES('Hähnchenbrust','haehnchenbrust','01a0e7f4-8a49-7790-a800-e840e6092581','g',NULL,NULL,110.0,23.0,0.0,0.0,1.2,'01a0e7f4-9952-7024-a21f-c60df788c992','01a0e7f4-9952-7024-a21f-c60df788c992','01a0e7f4-998f-77ce-aaa4-1dc5dff6057f','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "ingredients" VALUES('Hackfleisch','hackfleisch','01a0e7f4-8a49-7790-a800-e840e6092581','g',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'01a0e7f4-994b-76eb-9ac0-d721e855fb70','01a0e7f4-994b-76eb-9ac0-d721e855fb70','01a0e7f4-9990-734e-96aa-c9a303be62fc','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "ingredients" VALUES('Salami','salami','01a0e7f4-8a49-7790-a800-e8412257111f','g',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'01a0e7f4-9957-73c7-9e4b-f263774bc144','01a0e7f4-9957-73c7-9e4b-f263774bc144','01a0e7f4-9992-7614-8136-50b6560f8986','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "ingredients" VALUES('Tofu','tofu','01a0e7f4-8a49-7790-a800-e842c900c62f','g',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'01a0e7f4-9957-73c7-9e4b-f263774bc144','01a0e7f4-9957-73c7-9e4b-f263774bc144','01a0e7f4-9993-7434-8297-1c18612e9a85','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "ingredients" VALUES('Spaghetti','spaghetti','01a0e7f4-8a49-7790-a800-e84364691afd','g',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'01a0e7f4-994b-76eb-9ac0-d721e855fb70','01a0e7f4-994b-76eb-9ac0-d721e855fb70','01a0e7f4-9994-74f9-8555-4a4150586165','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "ingredients" VALUES('Reis','reis','01a0e7f4-8a49-7790-a800-e84364691afd','g',NULL,NULL,350.0,7.0,78.0,0.2,0.6,'01a0e7f4-9952-7024-a21f-c60df788c992','01a0e7f4-9952-7024-a21f-c60df788c992','01a0e7f4-9996-7141-8872-e59663e0d8fe','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "ingredients" VALUES('Passierte Tomaten','passierte tomaten','01a0e7f4-8a49-7790-a800-e844336f42bf','g',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'01a0e7f4-994b-76eb-9ac0-d721e855fb70','01a0e7f4-994b-76eb-9ac0-d721e855fb70','01a0e7f4-9997-7618-abe0-56163629796d','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "ingredients" VALUES('Olivenöl','olivenoel','01a0e7f4-8a49-7790-a800-e8451ad739d5','ml',NULL,0.92,NULL,NULL,NULL,NULL,NULL,'01a0e7f4-9952-7024-a21f-c60df788c992','01a0e7f4-9952-7024-a21f-c60df788c992','01a0e7f4-9998-74e2-83e9-6aa9f3f25848','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "ingredients" VALUES('Salz','salz','01a0e7f4-8a49-7790-a800-e8451ad739d5','g',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'01a0e7f4-9952-7024-a21f-c60df788c992','01a0e7f4-9952-7024-a21f-c60df788c992','01a0e7f4-9999-73ef-9c36-7f4eb9bbc6ba','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "ingredients" VALUES('Pfeffer','pfeffer','01a0e7f4-8a49-7790-a800-e8451ad739d5','g',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'01a0e7f4-9957-73c7-9e4b-f263774bc144','01a0e7f4-9957-73c7-9e4b-f263774bc144','01a0e7f4-999b-76e8-99b6-feae8169af4d','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "ingredients" VALUES('Mehl','mehl','01a0e7f4-8a49-7790-a800-e8467e1f0b87','g',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'01a0e7f4-9957-73c7-9e4b-f263774bc144','01a0e7f4-9957-73c7-9e4b-f263774bc144','01a0e7f4-999c-7554-afdb-6a589e4d21ee','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "ingredients" VALUES('Zucker','zucker','01a0e7f4-8a49-7790-a800-e8467e1f0b87','g',NULL,NULL,400.0,0.0,100.0,100.0,0.0,'01a0e7f4-994b-76eb-9ac0-d721e855fb70','01a0e7f4-994b-76eb-9ac0-d721e855fb70','01a0e7f4-999d-709a-99d7-334b3489e58d','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "ingredients" VALUES('Erdbeermarmelade','erdbeermarmelade','01a0e7f4-8a49-7790-a800-e84720d7b97a','g',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'01a0e7f4-9952-7024-a21f-c60df788c992','01a0e7f4-9952-7024-a21f-c60df788c992','01a0e7f4-999e-75b0-8bd6-05664ebbc509','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "ingredients" VALUES('Zartbitterschokolade','zartbitterschokolade','01a0e7f4-8a49-7790-a800-e8484c3f43e5','g',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'01a0e7f4-9957-73c7-9e4b-f263774bc144','01a0e7f4-9957-73c7-9e4b-f263774bc144','01a0e7f4-99a0-7331-b538-75c0ee095d31','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "ingredients" VALUES('Erbsen (TK)','erbsen (tk)','01a0e7f4-8a49-7790-a800-e8491be9655b','g',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'01a0e7f4-994b-76eb-9ac0-d721e855fb70','01a0e7f4-994b-76eb-9ac0-d721e855fb70','01a0e7f4-99a1-7567-8e22-45524893b438','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "ingredients" VALUES('Kaffee','kaffee','01a0e7f4-8a49-7790-a800-e84a287fa151','g',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'01a0e7f4-9957-73c7-9e4b-f263774bc144','01a0e7f4-9957-73c7-9e4b-f263774bc144','01a0e7f4-99a2-7516-a3b8-4d7ae679952f','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
CREATE TABLE list_extra_items (
	list_id VARCHAR(36) NOT NULL,
	ingredient_id VARCHAR(36),
	attrs_snapshot JSON,
	text VARCHAR(80),
	amount FLOAT,
	unit VARCHAR(10),
	amount_text VARCHAR(30),
	category_id VARCHAR(36),
	added_by VARCHAR(36),
	deleted_at DATETIME,
	id VARCHAR(36) NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	CONSTRAINT pk_list_extra_items PRIMARY KEY (id),
	CONSTRAINT ck_list_extra_items_ingredient_or_text CHECK ((ingredient_id IS NULL) <> (text IS NULL)),
	CONSTRAINT ck_list_extra_items_amount CHECK (amount IS NULL OR amount > 0),
	CONSTRAINT ck_list_extra_items_amount_or_amount_text CHECK (amount IS NULL OR amount_text IS NULL),
	CONSTRAINT ck_list_extra_items_unit_needs_amount CHECK (unit IS NULL OR amount IS NOT NULL),
	CONSTRAINT fk_list_extra_items_added_by_users FOREIGN KEY(added_by) REFERENCES users (id) ON DELETE SET NULL,
	CONSTRAINT fk_list_extra_items_category_id_categories FOREIGN KEY(category_id) REFERENCES categories (id) ON DELETE RESTRICT,
	CONSTRAINT fk_list_extra_items_ingredient_id_ingredients FOREIGN KEY(ingredient_id) REFERENCES ingredients (id) ON DELETE RESTRICT,
	CONSTRAINT fk_list_extra_items_list_id_shopping_lists FOREIGN KEY(list_id) REFERENCES shopping_lists (id) ON DELETE CASCADE
);
INSERT INTO "list_extra_items" VALUES('01a0e7f4-99f5-7755-a482-0470341b21ab','01a0e7f4-9979-721c-a25b-f58ead9f540a',NULL,NULL,6.0,'piece',NULL,NULL,'01a0e7f4-994b-76eb-9ac0-d721e855fb70',NULL,'01a0e7f4-99f8-76f5-8a78-5afc1e73aaa2','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "list_extra_items" VALUES('01a0e7f4-99f5-7755-a482-0470341b21ab','01a0e7f4-997c-72da-a684-55e358d4756f',NULL,NULL,NULL,NULL,NULL,NULL,'01a0e7f4-994b-76eb-9ac0-d721e855fb70',NULL,'01a0e7f4-99f8-76f5-8a78-5afd860a9537','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "list_extra_items" VALUES('01a0e7f4-99f5-7755-a482-0470341b21ab',NULL,NULL,'Geburtstagskerzen',NULL,NULL,'1 Packung','01a0e7f4-8a49-7790-a800-e84c01f4b0e9','01a0e7f4-994b-76eb-9ac0-d721e855fb70',NULL,'01a0e7f4-99f8-76f5-8a78-5afedfd5fc0c','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "list_extra_items" VALUES('01a0e7f4-9a01-712d-81a4-5611e0dbe5ba',NULL,NULL,'Grillkohle',NULL,NULL,'2 Säcke','01a0e7f4-8a49-7790-a800-e84c01f4b0e9','01a0e7f4-9957-73c7-9e4b-f263774bc144',NULL,'01a0e7f4-9a03-7669-9254-778a7096d664','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "list_extra_items" VALUES('01a0e7f4-9a05-70ae-844d-2d026b5fa724','01a0e7f4-9986-779f-ad93-ea1b6428cf11','{"name": "Milch", "base_unit": "ml", "piece_weight_g": null, "density_g_per_ml": 1.03, "category_id": "01a0e7f4-8a49-7790-a800-e83e5672f26e"}',NULL,1.0,'l',NULL,NULL,'01a0e7f4-994b-76eb-9ac0-d721e855fb70',NULL,'01a0e7f4-9a07-7436-a9f9-96e9aa1191e6','2026-09-28 12:19:20.444234','2026-09-28 12:19:22.325484');
INSERT INTO "list_extra_items" VALUES('01a0e7f4-9a05-70ae-844d-2d026b5fa724',NULL,NULL,'Küchenrolle',NULL,NULL,NULL,'01a0e7f4-8a49-7790-a800-e84c01f4b0e9','01a0e7f4-994b-76eb-9ac0-d721e855fb70',NULL,'01a0e7f4-9a07-7436-a9f9-96eac82f82e3','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "list_extra_items" VALUES('01a0e7f4-9a05-70ae-844d-2d026b5fa724','01a0e7f4-99a2-7516-a3b8-4d7ae679952f','{"name": "Kaffee", "base_unit": "g", "piece_weight_g": null, "density_g_per_ml": null, "category_id": "01a0e7f4-8a49-7790-a800-e84a287fa151"}',NULL,500.0,'g',NULL,NULL,'01a0e7f4-994b-76eb-9ac0-d721e855fb70',NULL,'01a0e7f4-9a88-7391-aa2b-36998defdb25','2026-09-28 12:19:20.444234','2026-09-28 12:19:22.381727');
INSERT INTO "list_extra_items" VALUES('01a0e7f4-9a8f-75ea-9d47-92612588bfda','01a0e7f4-9984-7740-a316-18429919b60f','{"name": "Brot", "base_unit": "g", "piece_weight_g": null, "density_g_per_ml": null, "category_id": "01a0e7f4-8a49-7790-a800-e83d1da5a177"}',NULL,1.0,'piece',NULL,NULL,'01a0e7f4-994b-76eb-9ac0-d721e855fb70',NULL,'01a0e7f4-9a90-7241-b853-150a7079018a','2026-09-28 12:19:20.444234','2026-09-28 12:19:22.403861');
INSERT INTO "list_extra_items" VALUES('01a0e7f4-9ac6-700f-ba36-fc9a48edd448',NULL,NULL,'Spülmittel',NULL,NULL,'1 Flasche','01a0e7f4-8a49-7790-a800-e84c01f4b0e9','01a0e7f4-9957-73c7-9e4b-f263774bc144',NULL,'01a0e7f4-9ac8-7336-b4a7-abd7787b21a9','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
CREATE TABLE list_line_states (
	list_id VARCHAR(36) NOT NULL,
	line_key VARCHAR(80) NOT NULL,
	checked BOOLEAN NOT NULL,
	checked_at DATETIME,
	checked_op_id VARCHAR(36),
	checked_by VARCHAR(36),
	checked_snapshot JSON,
	hidden BOOLEAN NOT NULL,
	CONSTRAINT pk_list_line_states PRIMARY KEY (list_id, line_key),
	CONSTRAINT fk_list_line_states_checked_by_users FOREIGN KEY(checked_by) REFERENCES users (id) ON DELETE SET NULL,
	CONSTRAINT fk_list_line_states_list_id_shopping_lists FOREIGN KEY(list_id) REFERENCES shopping_lists (id) ON DELETE CASCADE
);
INSERT INTO "list_line_states" VALUES('01a0e7f4-99f5-7755-a482-0470341b21ab','i:01a0e7f4-9999-73ef-9c36-7f4eb9bbc6ba',0,NULL,NULL,NULL,NULL,1);
INSERT INTO "list_line_states" VALUES('01a0e7f4-9a05-70ae-844d-2d026b5fa724','i:01a0e7f4-997c-72da-a684-55e358d4756f',1,'2026-09-28 11:22:20.444234','01a0e7f4-9a83-75ac-8026-1735ad9fa3f4','01a0e7f4-994b-76eb-9ac0-d721e855fb70','{"count": 2.0, "has_unspecified": false, "base_total": 300.0, "base_unit": "g"}',0);
INSERT INTO "list_line_states" VALUES('01a0e7f4-9a05-70ae-844d-2d026b5fa724','i:01a0e7f4-997e-742f-8983-096a5633adbe',0,NULL,NULL,NULL,NULL,0);
INSERT INTO "list_line_states" VALUES('01a0e7f4-9a05-70ae-844d-2d026b5fa724','i:01a0e7f4-9983-7750-a00d-c9a34a1781bb',0,NULL,NULL,NULL,NULL,0);
INSERT INTO "list_line_states" VALUES('01a0e7f4-9a05-70ae-844d-2d026b5fa724','i:01a0e7f4-9986-779f-ad93-ea1b6428cf11',1,'2026-09-28 11:21:20.444234','01a0e7f4-9a82-72a8-9ba6-8c63bd8b4cea','01a0e7f4-994b-76eb-9ac0-d721e855fb70','{"volume_ml": 1000.0, "has_unspecified": false, "base_total": 1000.0, "base_unit": "ml"}',0);
INSERT INTO "list_line_states" VALUES('01a0e7f4-9a05-70ae-844d-2d026b5fa724','i:01a0e7f4-998d-723c-bc7d-5b8d305b0d0d',0,NULL,NULL,NULL,NULL,0);
INSERT INTO "list_line_states" VALUES('01a0e7f4-9a05-70ae-844d-2d026b5fa724','i:01a0e7f4-998f-77ce-aaa4-1dc5dff6057f',0,NULL,NULL,NULL,NULL,0);
INSERT INTO "list_line_states" VALUES('01a0e7f4-9a05-70ae-844d-2d026b5fa724','i:01a0e7f4-9990-734e-96aa-c9a303be62fc',1,'2026-09-28 11:23:20.444234','01a0e7f4-9a85-7309-a4a8-52d82ada1fe8','01a0e7f4-9952-7024-a21f-c60df788c992','{"mass_g": 400.0, "has_unspecified": false, "base_total": 400.0, "base_unit": "g"}',0);
INSERT INTO "list_line_states" VALUES('01a0e7f4-9a05-70ae-844d-2d026b5fa724','i:01a0e7f4-9994-74f9-8555-4a4150586165',1,'2026-09-28 11:20:20.444234','01a0e7f4-9a7f-70f9-bf84-1a6485d48b6a','01a0e7f4-994b-76eb-9ac0-d721e855fb70','{"mass_g": 500.0, "has_unspecified": false, "base_total": 500.0, "base_unit": "g"}',0);
INSERT INTO "list_line_states" VALUES('01a0e7f4-9a05-70ae-844d-2d026b5fa724','i:01a0e7f4-9996-7141-8872-e59663e0d8fe',0,NULL,NULL,NULL,NULL,0);
INSERT INTO "list_line_states" VALUES('01a0e7f4-9a05-70ae-844d-2d026b5fa724','i:01a0e7f4-9997-7618-abe0-56163629796d',0,NULL,NULL,NULL,NULL,0);
INSERT INTO "list_line_states" VALUES('01a0e7f4-9a05-70ae-844d-2d026b5fa724','i:01a0e7f4-9998-74e2-83e9-6aa9f3f25848',0,NULL,NULL,NULL,NULL,0);
INSERT INTO "list_line_states" VALUES('01a0e7f4-9a05-70ae-844d-2d026b5fa724','i:01a0e7f4-9999-73ef-9c36-7f4eb9bbc6ba',0,NULL,NULL,NULL,NULL,0);
INSERT INTO "list_line_states" VALUES('01a0e7f4-9a05-70ae-844d-2d026b5fa724','i:01a0e7f4-999b-76e8-99b6-feae8169af4d',0,NULL,NULL,NULL,NULL,0);
INSERT INTO "list_line_states" VALUES('01a0e7f4-9a05-70ae-844d-2d026b5fa724','i:01a0e7f4-99a1-7567-8e22-45524893b438',0,NULL,NULL,NULL,NULL,0);
INSERT INTO "list_line_states" VALUES('01a0e7f4-9a05-70ae-844d-2d026b5fa724','x:01a0e7f4-9a07-7436-a9f9-96eac82f82e3',0,NULL,NULL,NULL,NULL,0);
INSERT INTO "list_line_states" VALUES('01a0e7f4-9a8f-75ea-9d47-92612588bfda','i:01a0e7f4-997c-72da-a684-55e358d4756f',1,'2026-09-26 10:21:20.444234','01a0e7f4-9abe-7554-9058-3c655d07c6f5','01a0e7f4-9952-7024-a21f-c60df788c992','{"count": 1.0, "has_unspecified": false, "base_total": 150.0, "base_unit": "g"}',0);
INSERT INTO "list_line_states" VALUES('01a0e7f4-9a8f-75ea-9d47-92612588bfda','i:01a0e7f4-997f-71a4-b0c9-d01d591f9b00',1,'2026-09-26 10:20:20.444234','01a0e7f4-9abc-72e5-861e-7cacc5f96ccf','01a0e7f4-9952-7024-a21f-c60df788c992','{"count": 8.0, "has_unspecified": false, "base_total": 800.0, "base_unit": "g"}',0);
INSERT INTO "list_line_states" VALUES('01a0e7f4-9a8f-75ea-9d47-92612588bfda','i:01a0e7f4-9984-7740-a316-18429919b60f',1,'2026-09-26 10:23:20.444234','01a0e7f4-9ac2-7637-839b-785f6025be00','01a0e7f4-994b-76eb-9ac0-d721e855fb70','{"count": 1.0, "has_unspecified": false}',0);
INSERT INTO "list_line_states" VALUES('01a0e7f4-9a8f-75ea-9d47-92612588bfda','i:01a0e7f4-9998-74e2-83e9-6aa9f3f25848',1,'2026-09-26 10:22:20.444234','01a0e7f4-9ac0-73e9-9811-6c266752b7be','01a0e7f4-994b-76eb-9ac0-d721e855fb70','{"volume_ml": 90.0, "has_unspecified": false, "base_total": 90.0, "base_unit": "ml"}',0);
INSERT INTO "list_line_states" VALUES('01a0e7f4-9a8f-75ea-9d47-92612588bfda','i:01a0e7f4-9999-73ef-9c36-7f4eb9bbc6ba',1,'2026-09-26 10:24:20.444234','01a0e7f4-9ac3-71d2-825a-d7d615768eb8','01a0e7f4-994b-76eb-9ac0-d721e855fb70','{"has_unspecified": true}',0);
INSERT INTO "list_line_states" VALUES('01a0e7f4-9a8f-75ea-9d47-92612588bfda','i:01a0e7f4-999b-76e8-99b6-feae8169af4d',0,NULL,NULL,NULL,NULL,0);
INSERT INTO "list_line_states" VALUES('01a0e7f4-9ac6-700f-ba36-fc9a48edd448','i:01a0e7f4-997c-72da-a684-55e358d4756f',1,'2026-09-19 11:22:20.444234','01a0e7f4-9af6-76ca-887a-ae4adc2da149','01a0e7f4-9957-73c7-9e4b-f263774bc144','{"count": 1.0, "has_unspecified": false, "base_total": 150.0, "base_unit": "g"}',0);
INSERT INTO "list_line_states" VALUES('01a0e7f4-9ac6-700f-ba36-fc9a48edd448','i:01a0e7f4-9983-7750-a00d-c9a34a1781bb',1,'2026-09-19 11:21:20.444234','01a0e7f4-9af4-7084-a9b3-a5eb2fe48cd6','01a0e7f4-9957-73c7-9e4b-f263774bc144','{"count": 3.0, "has_unspecified": false, "base_total": 240.0, "base_unit": "g"}',0);
INSERT INTO "list_line_states" VALUES('01a0e7f4-9ac6-700f-ba36-fc9a48edd448','i:01a0e7f4-9993-7434-8297-1c18612e9a85',1,'2026-09-19 11:20:20.444234','01a0e7f4-9af2-7194-8376-4c6eb8ea88f3','01a0e7f4-9957-73c7-9e4b-f263774bc144','{"mass_g": 400.0, "has_unspecified": false, "base_total": 400.0, "base_unit": "g"}',0);
INSERT INTO "list_line_states" VALUES('01a0e7f4-9ac6-700f-ba36-fc9a48edd448','i:01a0e7f4-9996-7141-8872-e59663e0d8fe',1,'2026-09-19 11:23:20.444234','01a0e7f4-9af7-706e-86c1-9e0f7f382f3a','01a0e7f4-9957-73c7-9e4b-f263774bc144','{"mass_g": 250.0, "has_unspecified": false, "base_total": 250.0, "base_unit": "g"}',0);
INSERT INTO "list_line_states" VALUES('01a0e7f4-9ac6-700f-ba36-fc9a48edd448','i:01a0e7f4-9998-74e2-83e9-6aa9f3f25848',1,'2026-09-19 11:24:20.444234','01a0e7f4-9af8-74b8-be95-a3d7135ea6c8','01a0e7f4-9957-73c7-9e4b-f263774bc144','{"volume_ml": 15.0, "has_unspecified": false, "base_total": 15.0, "base_unit": "ml"}',0);
INSERT INTO "list_line_states" VALUES('01a0e7f4-9ac6-700f-ba36-fc9a48edd448','x:01a0e7f4-9ac8-7336-b4a7-abd7787b21a9',1,'2026-09-19 11:25:20.444234','01a0e7f4-9afa-723f-bcfc-5462083c2549','01a0e7f4-9957-73c7-9e4b-f263774bc144','{"has_unspecified": true, "text": "Sp\u00fclmittel", "amount_text": "1 Flasche"}',0);
CREATE TABLE list_meal_ingredients (
	list_meal_id VARCHAR(36) NOT NULL,
	position INTEGER NOT NULL,
	ingredient_id VARCHAR(36) NOT NULL,
	ingredient_name_snapshot VARCHAR(60) NOT NULL,
	base_unit_snapshot VARCHAR(2) NOT NULL,
	piece_weight_g_snapshot FLOAT,
	density_snapshot FLOAT,
	category_id_snapshot VARCHAR(36) NOT NULL,
	amount FLOAT,
	unit VARCHAR(10),
	note VARCHAR(80),
	id VARCHAR(36) NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	CONSTRAINT pk_list_meal_ingredients PRIMARY KEY (id),
	CONSTRAINT ck_list_meal_ingredients_base_unit_snapshot CHECK (base_unit_snapshot IN ('g', 'ml')),
	CONSTRAINT ck_list_meal_ingredients_amount CHECK (amount IS NULL OR amount > 0),
	CONSTRAINT ck_list_meal_ingredients_position CHECK (position >= 0),
	CONSTRAINT ck_list_meal_ingredients_unit_needs_amount CHECK (unit IS NULL OR amount IS NOT NULL),
	CONSTRAINT fk_list_meal_ingredients_category_id_snapshot_categories FOREIGN KEY(category_id_snapshot) REFERENCES categories (id) ON DELETE RESTRICT,
	CONSTRAINT fk_list_meal_ingredients_ingredient_id_ingredients FOREIGN KEY(ingredient_id) REFERENCES ingredients (id) ON DELETE RESTRICT,
	CONSTRAINT fk_list_meal_ingredients_list_meal_id_list_meals FOREIGN KEY(list_meal_id) REFERENCES list_meals (id) ON DELETE CASCADE,
	CONSTRAINT uq_list_meal_ingredients_list_meal_id UNIQUE (list_meal_id, position)
);
INSERT INTO "list_meal_ingredients" VALUES('01a0e7f4-9a0c-731d-8c41-6a4a72fc2967',0,'01a0e7f4-9994-74f9-8555-4a4150586165','Spaghetti','g',NULL,NULL,'01a0e7f4-8a49-7790-a800-e84364691afd',500.0,'g',NULL,'01a0e7f4-9a38-77f7-addc-00b85a34fcbb','2026-09-28 11:19:20.444234','2026-09-28 11:19:20.444234');
INSERT INTO "list_meal_ingredients" VALUES('01a0e7f4-9a0c-731d-8c41-6a4a72fc2967',1,'01a0e7f4-9990-734e-96aa-c9a303be62fc','Hackfleisch','g',NULL,NULL,'01a0e7f4-8a49-7790-a800-e840e6092581',400.0,'g',NULL,'01a0e7f4-9a38-77f7-addc-00b9a5b744c6','2026-09-28 11:19:20.444234','2026-09-28 11:19:20.444234');
INSERT INTO "list_meal_ingredients" VALUES('01a0e7f4-9a0c-731d-8c41-6a4a72fc2967',2,'01a0e7f4-9997-7618-abe0-56163629796d','Passierte Tomaten','g',NULL,NULL,'01a0e7f4-8a49-7790-a800-e844336f42bf',700.0,'g',NULL,'01a0e7f4-9a38-77f7-addc-00bab7d54e07','2026-09-28 11:19:20.444234','2026-09-28 11:19:20.444234');
INSERT INTO "list_meal_ingredients" VALUES('01a0e7f4-9a0c-731d-8c41-6a4a72fc2967',3,'01a0e7f4-997c-72da-a684-55e358d4756f','Zwiebeln','g',150.0,NULL,'01a0e7f4-8a49-7790-a800-e83c059e51cc',1.0,'piece',NULL,'01a0e7f4-9a38-77f7-addc-00bbcf35e5e1','2026-09-28 11:19:20.444234','2026-09-28 11:19:20.444234');
INSERT INTO "list_meal_ingredients" VALUES('01a0e7f4-9a0c-731d-8c41-6a4a72fc2967',4,'01a0e7f4-997e-742f-8983-096a5633adbe','Knoblauch','g',5.0,NULL,'01a0e7f4-8a49-7790-a800-e83c059e51cc',2.0,'piece','fein gehackt','01a0e7f4-9a38-77f7-addc-00bcf38eb666','2026-09-28 11:19:20.444234','2026-09-28 11:19:20.444234');
INSERT INTO "list_meal_ingredients" VALUES('01a0e7f4-9a0c-731d-8c41-6a4a72fc2967',5,'01a0e7f4-9998-74e2-83e9-6aa9f3f25848','Olivenöl','ml',NULL,0.92,'01a0e7f4-8a49-7790-a800-e8451ad739d5',2.0,'tbsp',NULL,'01a0e7f4-9a38-77f7-addc-00bd46007a41','2026-09-28 11:19:20.444234','2026-09-28 11:19:20.444234');
INSERT INTO "list_meal_ingredients" VALUES('01a0e7f4-9a0c-731d-8c41-6a4a72fc2967',6,'01a0e7f4-998d-723c-bc7d-5b8d305b0d0d','Parmesan','g',NULL,NULL,'01a0e7f4-8a49-7790-a800-e83ffc117fc7',50.0,'g','gerieben','01a0e7f4-9a38-77f7-addc-00beb4f3db90','2026-09-28 11:19:20.444234','2026-09-28 11:19:20.444234');
INSERT INTO "list_meal_ingredients" VALUES('01a0e7f4-9a0c-731d-8c41-6a4a72fc2967',7,'01a0e7f4-9999-73ef-9c36-7f4eb9bbc6ba','Salz','g',NULL,NULL,'01a0e7f4-8a49-7790-a800-e8451ad739d5',NULL,NULL,'nach Geschmack','01a0e7f4-9a38-77f7-addc-00bf550c2dd9','2026-09-28 11:19:20.444234','2026-09-28 11:19:20.444234');
INSERT INTO "list_meal_ingredients" VALUES('01a0e7f4-9a0c-731d-8c41-6a4a72fc2967',8,'01a0e7f4-999b-76e8-99b6-feae8169af4d','Pfeffer','g',NULL,NULL,'01a0e7f4-8a49-7790-a800-e8451ad739d5',NULL,NULL,'nach Geschmack','01a0e7f4-9a38-77f7-addc-00c0fc514d23','2026-09-28 11:19:20.444234','2026-09-28 11:19:20.444234');
INSERT INTO "list_meal_ingredients" VALUES('01a0e7f4-9a0c-731d-8c41-6a4b05c01803',0,'01a0e7f4-998f-77ce-aaa4-1dc5dff6057f','Hähnchenbrust','g',NULL,NULL,'01a0e7f4-8a49-7790-a800-e840e6092581',300.0,'g','in Streifen','01a0e7f4-9a38-77f7-addc-00c18b0fbcbe','2026-09-28 11:19:20.444234','2026-09-28 11:19:20.444234');
INSERT INTO "list_meal_ingredients" VALUES('01a0e7f4-9a0c-731d-8c41-6a4b05c01803',1,'01a0e7f4-9996-7141-8872-e59663e0d8fe','Reis','g',NULL,NULL,'01a0e7f4-8a49-7790-a800-e84364691afd',200.0,'g',NULL,'01a0e7f4-9a38-77f7-addc-00c29f213e7c','2026-09-28 11:19:20.444234','2026-09-28 11:19:20.444234');
INSERT INTO "list_meal_ingredients" VALUES('01a0e7f4-9a0c-731d-8c41-6a4b05c01803',2,'01a0e7f4-99a1-7567-8e22-45524893b438','Erbsen (TK)','g',NULL,NULL,'01a0e7f4-8a49-7790-a800-e8491be9655b',150.0,'g',NULL,'01a0e7f4-9a38-77f7-addc-00c3b10f199b','2026-09-28 11:19:20.444234','2026-09-28 11:19:20.444234');
INSERT INTO "list_meal_ingredients" VALUES('01a0e7f4-9a0c-731d-8c41-6a4b05c01803',3,'01a0e7f4-9983-7750-a00d-c9a34a1781bb','Karotten','g',80.0,NULL,'01a0e7f4-8a49-7790-a800-e83c059e51cc',2.0,'piece',NULL,'01a0e7f4-9a38-77f7-addc-00c41d8978ad','2026-09-28 11:19:20.444234','2026-09-28 11:19:20.444234');
INSERT INTO "list_meal_ingredients" VALUES('01a0e7f4-9a0c-731d-8c41-6a4b05c01803',4,'01a0e7f4-997c-72da-a684-55e358d4756f','Zwiebeln','g',150.0,NULL,'01a0e7f4-8a49-7790-a800-e83c059e51cc',1.0,'piece',NULL,'01a0e7f4-9a38-77f7-addc-00c5c1762a9d','2026-09-28 11:19:20.444234','2026-09-28 11:19:20.444234');
INSERT INTO "list_meal_ingredients" VALUES('01a0e7f4-9a0c-731d-8c41-6a4b05c01803',5,'01a0e7f4-9998-74e2-83e9-6aa9f3f25848','Olivenöl','ml',NULL,0.92,'01a0e7f4-8a49-7790-a800-e8451ad739d5',1.0,'tbsp',NULL,'01a0e7f4-9a38-77f7-addc-00c67e08f6c4','2026-09-28 11:19:20.444234','2026-09-28 11:19:20.444234');
INSERT INTO "list_meal_ingredients" VALUES('01a0e7f4-9a91-77dd-8da6-72dd1490db28',0,'01a0e7f4-997f-71a4-b0c9-d01d591f9b00','Tomaten','g',100.0,NULL,'01a0e7f4-8a49-7790-a800-e83c059e51cc',4.0,'piece',NULL,'01a0e7f4-9a9d-727e-92ad-f8ed54c175f7','2026-09-26 10:19:20.444234','2026-09-26 10:19:20.444234');
INSERT INTO "list_meal_ingredients" VALUES('01a0e7f4-9a91-77dd-8da6-72dd1490db28',1,'01a0e7f4-997c-72da-a684-55e358d4756f','Zwiebeln','g',150.0,NULL,'01a0e7f4-8a49-7790-a800-e83c059e51cc',0.5,'piece',NULL,'01a0e7f4-9a9d-727e-92ad-f8ee79a021a9','2026-09-26 10:19:20.444234','2026-09-26 10:19:20.444234');
INSERT INTO "list_meal_ingredients" VALUES('01a0e7f4-9a91-77dd-8da6-72dd1490db28',2,'01a0e7f4-9998-74e2-83e9-6aa9f3f25848','Olivenöl','ml',NULL,0.92,'01a0e7f4-8a49-7790-a800-e8451ad739d5',3.0,'tbsp',NULL,'01a0e7f4-9a9d-727e-92ad-f8ef36515c9e','2026-09-26 10:19:20.444234','2026-09-26 10:19:20.444234');
INSERT INTO "list_meal_ingredients" VALUES('01a0e7f4-9a91-77dd-8da6-72dd1490db28',3,'01a0e7f4-9999-73ef-9c36-7f4eb9bbc6ba','Salz','g',NULL,NULL,'01a0e7f4-8a49-7790-a800-e8451ad739d5',NULL,NULL,'nach Geschmack','01a0e7f4-9a9d-727e-92ad-f8f0c3491096','2026-09-26 10:19:20.444234','2026-09-26 10:19:20.444234');
INSERT INTO "list_meal_ingredients" VALUES('01a0e7f4-9a91-77dd-8da6-72dd1490db28',4,'01a0e7f4-999b-76e8-99b6-feae8169af4d','Pfeffer','g',NULL,NULL,'01a0e7f4-8a49-7790-a800-e8451ad739d5',NULL,NULL,'nach Geschmack','01a0e7f4-9a9d-727e-92ad-f8f107ed3636','2026-09-26 10:19:20.444234','2026-09-26 10:19:20.444234');
INSERT INTO "list_meal_ingredients" VALUES('01a0e7f4-9ac8-7336-b4a7-abd8977f6c34',0,'01a0e7f4-9993-7434-8297-1c18612e9a85','Tofu','g',NULL,NULL,'01a0e7f4-8a49-7790-a800-e842c900c62f',400.0,'g',NULL,'01a0e7f4-9ad2-7412-8c1e-c0fdc4b2dc1d','2026-09-19 11:19:20.444234','2026-09-19 11:19:20.444234');
INSERT INTO "list_meal_ingredients" VALUES('01a0e7f4-9ac8-7336-b4a7-abd8977f6c34',1,'01a0e7f4-9983-7750-a00d-c9a34a1781bb','Karotten','g',80.0,NULL,'01a0e7f4-8a49-7790-a800-e83c059e51cc',3.0,'piece',NULL,'01a0e7f4-9ad2-7412-8c1e-c0fef9834b46','2026-09-19 11:19:20.444234','2026-09-19 11:19:20.444234');
INSERT INTO "list_meal_ingredients" VALUES('01a0e7f4-9ac8-7336-b4a7-abd8977f6c34',2,'01a0e7f4-997c-72da-a684-55e358d4756f','Zwiebeln','g',150.0,NULL,'01a0e7f4-8a49-7790-a800-e83c059e51cc',1.0,'piece',NULL,'01a0e7f4-9ad2-7412-8c1e-c0ff6ce3499c','2026-09-19 11:19:20.444234','2026-09-19 11:19:20.444234');
INSERT INTO "list_meal_ingredients" VALUES('01a0e7f4-9ac8-7336-b4a7-abd8977f6c34',3,'01a0e7f4-9996-7141-8872-e59663e0d8fe','Reis','g',NULL,NULL,'01a0e7f4-8a49-7790-a800-e84364691afd',250.0,'g',NULL,'01a0e7f4-9ad2-7412-8c1e-c1002eccb21c','2026-09-19 11:19:20.444234','2026-09-19 11:19:20.444234');
INSERT INTO "list_meal_ingredients" VALUES('01a0e7f4-9ac8-7336-b4a7-abd8977f6c34',4,'01a0e7f4-9998-74e2-83e9-6aa9f3f25848','Olivenöl','ml',NULL,0.92,'01a0e7f4-8a49-7790-a800-e8451ad739d5',1.0,'tbsp',NULL,'01a0e7f4-9ad2-7412-8c1e-c1013c279aeb','2026-09-19 11:19:20.444234','2026-09-19 11:19:20.444234');
INSERT INTO "list_meal_ingredients" VALUES('01a0e7f4-9a00-754d-a38b-990444812253',0,'01a0e7f4-9981-773a-998d-d7caf32e5885','Kartoffeln','g',150.0,NULL,'01a0e7f4-8a49-7790-a800-e83c059e51cc',800.0,'g',NULL,'01a0e7f4-9b0f-73e6-b83c-49a93e1d286b','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "list_meal_ingredients" VALUES('01a0e7f4-9a00-754d-a38b-990444812253',1,'01a0e7f4-9983-7750-a00d-c9a34a1781bb','Karotten','g',80.0,NULL,'01a0e7f4-8a49-7790-a800-e83c059e51cc',2.0,'piece',NULL,'01a0e7f4-9b10-76e9-a1ce-2b4fae95f9de','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "list_meal_ingredients" VALUES('01a0e7f4-9a00-754d-a38b-990444812253',2,'01a0e7f4-997c-72da-a684-55e358d4756f','Zwiebeln','g',150.0,NULL,'01a0e7f4-8a49-7790-a800-e83c059e51cc',1.0,'piece',NULL,'01a0e7f4-9b10-76e9-a1ce-2b50bcab940a','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "list_meal_ingredients" VALUES('01a0e7f4-9a00-754d-a38b-990444812253',3,'01a0e7f4-9999-73ef-9c36-7f4eb9bbc6ba','Salz','g',NULL,NULL,'01a0e7f4-8a49-7790-a800-e8451ad739d5',NULL,NULL,'nach Geschmack','01a0e7f4-9b10-76e9-a1ce-2b5124136ab8','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
CREATE TABLE list_meals (
	list_id VARCHAR(36) NOT NULL,
	meal_id VARCHAR(36),
	servings INTEGER NOT NULL,
	meal_servings_snapshot INTEGER NOT NULL,
	meal_name_snapshot VARCHAR(80) NOT NULL,
	meal_owner_id_snapshot VARCHAR(36),
	added_by VARCHAR(36),
	last_added_at DATETIME NOT NULL,
	frozen_at DATETIME,
	detached_reason VARCHAR(12),
	position INTEGER NOT NULL,
	id VARCHAR(36) NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	CONSTRAINT pk_list_meals PRIMARY KEY (id),
	CONSTRAINT ck_list_meals_detached_reason CHECK (detached_reason IS NULL OR detached_reason IN ('deleted', 'unavailable')),
	CONSTRAINT ck_list_meals_meal_servings_snapshot CHECK (meal_servings_snapshot >= 1),
	CONSTRAINT ck_list_meals_position CHECK (position >= 0),
	CONSTRAINT ck_list_meals_servings CHECK (servings >= 1 AND servings <= 99),
	CONSTRAINT fk_list_meals_added_by_users FOREIGN KEY(added_by) REFERENCES users (id) ON DELETE SET NULL,
	CONSTRAINT fk_list_meals_list_id_shopping_lists FOREIGN KEY(list_id) REFERENCES shopping_lists (id) ON DELETE CASCADE,
	CONSTRAINT fk_list_meals_meal_id_meals FOREIGN KEY(meal_id) REFERENCES meals (id) ON DELETE SET NULL,
	CONSTRAINT fk_list_meals_meal_owner_id_snapshot_users FOREIGN KEY(meal_owner_id_snapshot) REFERENCES users (id) ON DELETE SET NULL
);
INSERT INTO "list_meals" VALUES('01a0e7f4-99f5-7755-a482-0470341b21ab','01a0e7f4-99bf-7362-b953-161627d78c42',4,2,'Pfannkuchen','01a0e7f4-994b-76eb-9ac0-d721e855fb70','01a0e7f4-994b-76eb-9ac0-d721e855fb70','2026-09-28 12:19:20.444234',NULL,NULL,0,'01a0e7f4-99fc-77dc-9225-165f562e6232','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "list_meals" VALUES('01a0e7f4-99f5-7755-a482-0470341b21ab','01a0e7f4-99cf-754c-b781-d99da821e42f',3,2,'Tomatensalat','01a0e7f4-9952-7024-a21f-c60df788c992','01a0e7f4-994b-76eb-9ac0-d721e855fb70','2026-09-28 12:19:20.444234',NULL,NULL,1,'01a0e7f4-99fc-77dc-9225-166067166af1','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "list_meals" VALUES('01a0e7f4-99ff-70f4-a0a6-41f918d3e4fd','01a0e7f4-99ca-7016-bbc6-45047b523054',2,2,'Hähnchen-Reis-Pfanne','01a0e7f4-9952-7024-a21f-c60df788c992','01a0e7f4-9952-7024-a21f-c60df788c992','2026-09-28 12:19:20.444234',NULL,NULL,0,'01a0e7f4-9a00-754d-a38b-9903df146654','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "list_meals" VALUES('01a0e7f4-99ff-70f4-a0a6-41f918d3e4fd',NULL,4,4,'Kartoffelsuppe','01a0e7f4-9952-7024-a21f-c60df788c992','01a0e7f4-9952-7024-a21f-c60df788c992','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234','deleted',1,'01a0e7f4-9a00-754d-a38b-990444812253','2026-09-28 12:19:20.444234','2026-09-28 12:19:22.515569');
INSERT INTO "list_meals" VALUES('01a0e7f4-9a01-712d-81a4-5611e0dbe5ba','01a0e7f4-99dc-75cd-ada1-ac208fdd4faf',4,2,'Tofu-Gemüse-Curry','01a0e7f4-9957-73c7-9e4b-f263774bc144','01a0e7f4-9957-73c7-9e4b-f263774bc144','2026-09-28 12:19:20.444234',NULL,NULL,0,'01a0e7f4-9a04-73cf-a32c-83a5b824f08f','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "list_meals" VALUES('01a0e7f4-9a01-712d-81a4-5611e0dbe5ba','01a0e7f4-99b2-7427-8d3b-a16e0fc03731',2,4,'Spaghetti Bolognese','01a0e7f4-994b-76eb-9ac0-d721e855fb70','01a0e7f4-9957-73c7-9e4b-f263774bc144','2026-09-28 12:19:20.444234',NULL,NULL,1,'01a0e7f4-9a04-73cf-a32c-83a60b9a6148','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "list_meals" VALUES('01a0e7f4-9a05-70ae-844d-2d026b5fa724','01a0e7f4-99b2-7427-8d3b-a16e0fc03731',4,4,'Spaghetti Bolognese','01a0e7f4-994b-76eb-9ac0-d721e855fb70','01a0e7f4-994b-76eb-9ac0-d721e855fb70','2026-09-28 12:19:20.444234','2026-09-28 11:19:20.444234',NULL,0,'01a0e7f4-9a0c-731d-8c41-6a4a72fc2967','2026-09-28 12:19:20.444234','2026-09-28 11:19:20.444234');
INSERT INTO "list_meals" VALUES('01a0e7f4-9a05-70ae-844d-2d026b5fa724','01a0e7f4-99ca-7016-bbc6-45047b523054',4,2,'Hähnchen-Reis-Pfanne','01a0e7f4-9952-7024-a21f-c60df788c992','01a0e7f4-994b-76eb-9ac0-d721e855fb70','2026-09-28 12:19:20.444234','2026-09-28 11:19:20.444234',NULL,1,'01a0e7f4-9a0c-731d-8c41-6a4b05c01803','2026-09-28 12:19:20.444234','2026-09-28 12:19:22.378297');
INSERT INTO "list_meals" VALUES('01a0e7f4-9a8f-75ea-9d47-92612588bfda','01a0e7f4-99cf-754c-b781-d99da821e42f',4,2,'Tomatensalat','01a0e7f4-9952-7024-a21f-c60df788c992','01a0e7f4-994b-76eb-9ac0-d721e855fb70','2026-09-28 12:19:20.444234','2026-09-26 10:19:20.444234',NULL,0,'01a0e7f4-9a91-77dd-8da6-72dd1490db28','2026-09-28 12:19:20.444234','2026-09-26 10:19:20.444234');
INSERT INTO "list_meals" VALUES('01a0e7f4-9ac6-700f-ba36-fc9a48edd448','01a0e7f4-99dc-75cd-ada1-ac208fdd4faf',2,2,'Tofu-Gemüse-Curry','01a0e7f4-9957-73c7-9e4b-f263774bc144','01a0e7f4-9957-73c7-9e4b-f263774bc144','2026-09-28 12:19:20.444234','2026-09-19 11:19:20.444234',NULL,0,'01a0e7f4-9ac8-7336-b4a7-abd8977f6c34','2026-09-28 12:19:20.444234','2026-09-19 11:19:20.444234');
CREATE TABLE meal_ingredients (
	meal_id VARCHAR(36) NOT NULL,
	position INTEGER NOT NULL,
	ingredient_id VARCHAR(36) NOT NULL,
	amount FLOAT,
	unit VARCHAR(10),
	note VARCHAR(80),
	id VARCHAR(36) NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	CONSTRAINT pk_meal_ingredients PRIMARY KEY (id),
	CONSTRAINT ck_meal_ingredients_amount CHECK (amount IS NULL OR amount > 0),
	CONSTRAINT ck_meal_ingredients_position CHECK (position >= 0),
	CONSTRAINT ck_meal_ingredients_unit_needs_amount CHECK (unit IS NULL OR amount IS NOT NULL),
	CONSTRAINT fk_meal_ingredients_ingredient_id_ingredients FOREIGN KEY(ingredient_id) REFERENCES ingredients (id) ON DELETE RESTRICT,
	CONSTRAINT fk_meal_ingredients_meal_id_meals FOREIGN KEY(meal_id) REFERENCES meals (id) ON DELETE CASCADE,
	CONSTRAINT uq_meal_ingredients_meal_id UNIQUE (meal_id, position)
);
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99b2-7427-8d3b-a16e0fc03731',0,'01a0e7f4-9994-74f9-8555-4a4150586165',500.0,'g',NULL,'01a0e7f4-99c1-75bd-b972-4af4d045b9da','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99b2-7427-8d3b-a16e0fc03731',1,'01a0e7f4-9990-734e-96aa-c9a303be62fc',400.0,'g',NULL,'01a0e7f4-99c1-75bd-b972-4af50dfb510f','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99b2-7427-8d3b-a16e0fc03731',2,'01a0e7f4-9997-7618-abe0-56163629796d',700.0,'g',NULL,'01a0e7f4-99c1-75bd-b972-4af676a3f6b3','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99b2-7427-8d3b-a16e0fc03731',3,'01a0e7f4-997c-72da-a684-55e358d4756f',1.0,'piece',NULL,'01a0e7f4-99c1-75bd-b972-4af71715df4c','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99b2-7427-8d3b-a16e0fc03731',4,'01a0e7f4-997e-742f-8983-096a5633adbe',2.0,'piece','fein gehackt','01a0e7f4-99c1-75bd-b972-4af878258e99','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99b2-7427-8d3b-a16e0fc03731',5,'01a0e7f4-9998-74e2-83e9-6aa9f3f25848',2.0,'tbsp',NULL,'01a0e7f4-99c1-75bd-b972-4af9d0aa52cc','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99b2-7427-8d3b-a16e0fc03731',6,'01a0e7f4-998d-723c-bc7d-5b8d305b0d0d',50.0,'g','gerieben','01a0e7f4-99c2-7472-ab44-7efbf84f1688','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99b2-7427-8d3b-a16e0fc03731',7,'01a0e7f4-9999-73ef-9c36-7f4eb9bbc6ba',NULL,NULL,'nach Geschmack','01a0e7f4-99c2-7472-ab44-7efcb39040ad','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99b2-7427-8d3b-a16e0fc03731',8,'01a0e7f4-999b-76e8-99b6-feae8169af4d',NULL,NULL,'nach Geschmack','01a0e7f4-99c2-7472-ab44-7efd0eee90e2','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99bf-7362-b953-161627d78c42',0,'01a0e7f4-999c-7554-afdb-6a589e4d21ee',200.0,'g',NULL,'01a0e7f4-99cc-71fa-87ca-151bac8f5cc3','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99bf-7362-b953-161627d78c42',1,'01a0e7f4-9986-779f-ad93-ea1b6428cf11',300.0,'ml',NULL,'01a0e7f4-99cc-71fa-87ca-151c5ee557eb','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99bf-7362-b953-161627d78c42',2,'01a0e7f4-9987-7723-89ce-9fd84073140c',2.0,'piece',NULL,'01a0e7f4-99cc-71fa-87ca-151d91f70ffc','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99bf-7362-b953-161627d78c42',3,'01a0e7f4-999d-709a-99d7-334b3489e58d',1.0,'tbsp',NULL,'01a0e7f4-99cc-71fa-87ca-151e2b8616a7','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99bf-7362-b953-161627d78c42',4,'01a0e7f4-9999-73ef-9c36-7f4eb9bbc6ba',NULL,NULL,'1 Prise','01a0e7f4-99cc-71fa-87ca-151fe7103773','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99bf-7362-b953-161627d78c42',5,'01a0e7f4-9989-74dd-a236-202559a213b8',1.0,'tbsp','zum Braten','01a0e7f4-99cc-71fa-87ca-1520829de0e7','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99ca-7016-bbc6-45047b523054',0,'01a0e7f4-998f-77ce-aaa4-1dc5dff6057f',300.0,'g','in Streifen','01a0e7f4-99d0-7626-83d7-8cb935e3fefe','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99ca-7016-bbc6-45047b523054',1,'01a0e7f4-9996-7141-8872-e59663e0d8fe',200.0,'g',NULL,'01a0e7f4-99d0-7626-83d7-8cbaae71d687','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99ca-7016-bbc6-45047b523054',2,'01a0e7f4-99a1-7567-8e22-45524893b438',150.0,'g',NULL,'01a0e7f4-99d0-7626-83d7-8cbbafa31086','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99ca-7016-bbc6-45047b523054',3,'01a0e7f4-9983-7750-a00d-c9a34a1781bb',2.0,'piece',NULL,'01a0e7f4-99d0-7626-83d7-8cbcb72c44b4','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99ca-7016-bbc6-45047b523054',4,'01a0e7f4-997c-72da-a684-55e358d4756f',1.0,'piece',NULL,'01a0e7f4-99d0-7626-83d7-8cbd29b02198','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99ca-7016-bbc6-45047b523054',5,'01a0e7f4-9998-74e2-83e9-6aa9f3f25848',1.0,'tbsp',NULL,'01a0e7f4-99d0-7626-83d7-8cbec649072b','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99cf-754c-b781-d99da821e42f',0,'01a0e7f4-997f-71a4-b0c9-d01d591f9b00',4.0,'piece',NULL,'01a0e7f4-99d9-741d-ab27-60888c123ab5','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99cf-754c-b781-d99da821e42f',1,'01a0e7f4-997c-72da-a684-55e358d4756f',0.5,'piece',NULL,'01a0e7f4-99d9-741d-ab27-60895c0197fa','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99cf-754c-b781-d99da821e42f',2,'01a0e7f4-9998-74e2-83e9-6aa9f3f25848',3.0,'tbsp',NULL,'01a0e7f4-99d9-741d-ab27-608a670e3d1f','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99cf-754c-b781-d99da821e42f',3,'01a0e7f4-9999-73ef-9c36-7f4eb9bbc6ba',NULL,NULL,'nach Geschmack','01a0e7f4-99d9-741d-ab27-608b9eeedd6e','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99cf-754c-b781-d99da821e42f',4,'01a0e7f4-999b-76e8-99b6-feae8169af4d',NULL,NULL,'nach Geschmack','01a0e7f4-99d9-741d-ab27-608c59e7f1b7','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99d7-703c-b8df-4161384dea7c',0,'01a0e7f4-9981-773a-998d-d7caf32e5885',1.0,'kg',NULL,'01a0e7f4-99dd-724d-b639-8bf76dea2f92','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99d7-703c-b8df-4161384dea7c',1,'01a0e7f4-9998-74e2-83e9-6aa9f3f25848',2.0,'tbsp',NULL,'01a0e7f4-99dd-724d-b639-8bf8b0cde518','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99d7-703c-b8df-4161384dea7c',2,'01a0e7f4-998a-77fd-bc50-c98b5f18fa2d',250.0,'g',NULL,'01a0e7f4-99dd-724d-b639-8bf94e8457d7','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99d7-703c-b8df-4161384dea7c',3,'01a0e7f4-997e-742f-8983-096a5633adbe',1.0,'piece',NULL,'01a0e7f4-99dd-724d-b639-8bfae71d5141','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99d7-703c-b8df-4161384dea7c',4,'01a0e7f4-9999-73ef-9c36-7f4eb9bbc6ba',NULL,NULL,'nach Geschmack','01a0e7f4-99dd-724d-b639-8bfbf8336441','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99dc-75cd-ada1-ac208fdd4faf',0,'01a0e7f4-9993-7434-8297-1c18612e9a85',400.0,'g',NULL,'01a0e7f4-99e1-7111-b542-dd4d227a34ae','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99dc-75cd-ada1-ac208fdd4faf',1,'01a0e7f4-9983-7750-a00d-c9a34a1781bb',3.0,'piece',NULL,'01a0e7f4-99e1-7111-b542-dd4e5c5f905f','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99dc-75cd-ada1-ac208fdd4faf',2,'01a0e7f4-997c-72da-a684-55e358d4756f',1.0,'piece',NULL,'01a0e7f4-99e1-7111-b542-dd4f47667430','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99dc-75cd-ada1-ac208fdd4faf',3,'01a0e7f4-9996-7141-8872-e59663e0d8fe',250.0,'g',NULL,'01a0e7f4-99e1-7111-b542-dd50bcd69b97','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99dc-75cd-ada1-ac208fdd4faf',4,'01a0e7f4-9998-74e2-83e9-6aa9f3f25848',1.0,'tbsp',NULL,'01a0e7f4-99e1-7111-b542-dd517289a4b4','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99e0-7120-83f3-bb2c8094af3e',0,'01a0e7f4-9984-7740-a316-18429919b60f',2.0,'piece','Scheiben','01a0e7f4-99e5-7085-a0d8-815a5624e8bc','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99e0-7120-83f3-bb2c8094af3e',1,'01a0e7f4-9989-74dd-a236-202559a213b8',10.0,'g',NULL,'01a0e7f4-99e5-7085-a0d8-815b3532ee6d','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99e0-7120-83f3-bb2c8094af3e',2,'01a0e7f4-998c-73ce-81fa-dd459eb0c6d2',40.0,'g',NULL,'01a0e7f4-99e5-7085-a0d8-815c3ed414d3','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99e4-728b-8eda-cbb0d23d6949',0,'01a0e7f4-9994-74f9-8555-4a4150586165',500.0,'g',NULL,'01a0e7f4-99e8-7022-9679-d034d0bce1ab','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99e4-728b-8eda-cbb0d23d6949',1,'01a0e7f4-9990-734e-96aa-c9a303be62fc',400.0,'g',NULL,'01a0e7f4-99e8-7022-9679-d0353a5f096d','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99e4-728b-8eda-cbb0d23d6949',2,'01a0e7f4-9997-7618-abe0-56163629796d',700.0,'g',NULL,'01a0e7f4-99e8-7022-9679-d03675e53c46','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99e4-728b-8eda-cbb0d23d6949',3,'01a0e7f4-997c-72da-a684-55e358d4756f',1.0,'piece',NULL,'01a0e7f4-99e8-7022-9679-d03726f02ee9','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99e4-728b-8eda-cbb0d23d6949',4,'01a0e7f4-997e-742f-8983-096a5633adbe',2.0,'piece','fein gehackt','01a0e7f4-99e8-7022-9679-d038f93a8a33','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99e4-728b-8eda-cbb0d23d6949',5,'01a0e7f4-9998-74e2-83e9-6aa9f3f25848',2.0,'tbsp',NULL,'01a0e7f4-99e8-7022-9679-d039d323dbc6','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99e4-728b-8eda-cbb0d23d6949',6,'01a0e7f4-998d-723c-bc7d-5b8d305b0d0d',50.0,'g','gerieben','01a0e7f4-99e8-7022-9679-d03a6973af72','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99e4-728b-8eda-cbb0d23d6949',7,'01a0e7f4-9999-73ef-9c36-7f4eb9bbc6ba',NULL,NULL,'nach Geschmack','01a0e7f4-99e8-7022-9679-d03b18d1c140','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meal_ingredients" VALUES('01a0e7f4-99e4-728b-8eda-cbb0d23d6949',8,'01a0e7f4-999b-76e8-99b6-feae8169af4d',NULL,NULL,'nach Geschmack','01a0e7f4-99e8-7022-9679-d03ce166fbae','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
CREATE TABLE meal_tags (
	meal_id VARCHAR(36) NOT NULL,
	tag_id VARCHAR(36) NOT NULL,
	CONSTRAINT pk_meal_tags PRIMARY KEY (meal_id, tag_id),
	CONSTRAINT fk_meal_tags_meal_id_meals FOREIGN KEY(meal_id) REFERENCES meals (id) ON DELETE CASCADE,
	CONSTRAINT fk_meal_tags_tag_id_tags FOREIGN KEY(tag_id) REFERENCES tags (id) ON DELETE CASCADE
);
INSERT INTO "meal_tags" VALUES('01a0e7f4-99b2-7427-8d3b-a16e0fc03731','01a0e7f4-99b7-756d-a8af-6253a2dc5ca1');
INSERT INTO "meal_tags" VALUES('01a0e7f4-99b2-7427-8d3b-a16e0fc03731','01a0e7f4-99bc-73ee-b5f2-dce8af8b2493');
INSERT INTO "meal_tags" VALUES('01a0e7f4-99bf-7362-b953-161627d78c42','01a0e7f4-99c6-736d-9967-91bbbdbc797f');
INSERT INTO "meal_tags" VALUES('01a0e7f4-99bf-7362-b953-161627d78c42','01a0e7f4-99c8-7763-8143-d0330d7acd7b');
INSERT INTO "meal_tags" VALUES('01a0e7f4-99ca-7016-bbc6-45047b523054','01a0e7f4-99c8-7763-8143-d0330d7acd7b');
INSERT INTO "meal_tags" VALUES('01a0e7f4-99cf-754c-b781-d99da821e42f','01a0e7f4-99d3-73e2-9f8b-e3ceaf12afa9');
INSERT INTO "meal_tags" VALUES('01a0e7f4-99cf-754c-b781-d99da821e42f','01a0e7f4-99d5-715e-aaab-6a77d641534d');
INSERT INTO "meal_tags" VALUES('01a0e7f4-99d7-703c-b8df-4161384dea7c','01a0e7f4-99d3-73e2-9f8b-e3ceaf12afa9');
INSERT INTO "meal_tags" VALUES('01a0e7f4-99dc-75cd-ada1-ac208fdd4faf','01a0e7f4-99df-74a1-b820-4bf7a6e02b4b');
INSERT INTO "meal_tags" VALUES('01a0e7f4-99e0-7120-83f3-bb2c8094af3e','01a0e7f4-99e3-7324-82da-4d16c5a9c82c');
INSERT INTO "meal_tags" VALUES('01a0e7f4-99e0-7120-83f3-bb2c8094af3e','01a0e7f4-99c8-7763-8143-d0330d7acd7b');
INSERT INTO "meal_tags" VALUES('01a0e7f4-99e4-728b-8eda-cbb0d23d6949','01a0e7f4-99b7-756d-a8af-6253a2dc5ca1');
INSERT INTO "meal_tags" VALUES('01a0e7f4-99e4-728b-8eda-cbb0d23d6949','01a0e7f4-99bc-73ee-b5f2-dce8af8b2493');
CREATE TABLE meals (
	owner_id VARCHAR(36) NOT NULL,
	name VARCHAR(80) NOT NULL,
	name_norm VARCHAR(320) NOT NULL,
	instructions TEXT,
	source_url VARCHAR(2000),
	servings INTEGER NOT NULL,
	cuisine_id VARCHAR(36),
	photo_key VARCHAR(32),
	copied_from_meal_id VARCHAR(36),
	id VARCHAR(36) NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	CONSTRAINT pk_meals PRIMARY KEY (id),
	CONSTRAINT ck_meals_servings CHECK (servings >= 1),
	CONSTRAINT fk_meals_copied_from_meal_id_meals FOREIGN KEY(copied_from_meal_id) REFERENCES meals (id) ON DELETE SET NULL,
	CONSTRAINT fk_meals_cuisine_id_cuisines FOREIGN KEY(cuisine_id) REFERENCES cuisines (id) ON DELETE SET NULL,
	CONSTRAINT fk_meals_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE CASCADE
);
INSERT INTO "meals" VALUES('01a0e7f4-994b-76eb-9ac0-d721e855fb70','Spaghetti Bolognese','spaghetti bolognese','Zwiebeln und Knoblauch in Olivenöl andünsten.
Hackfleisch krümelig braten, passierte Tomaten dazugeben und 30 Minuten köcheln.
Mit Salz und Pfeffer abschmecken, mit den Spaghetti und Parmesan servieren.','https://de.wikipedia.org/wiki/Sauce_bolognese',4,'01a0e7f4-8a4a-7284-a550-c30253c8d564','bbd88b101e4046caa4daed027581d62a',NULL,'01a0e7f4-99b2-7427-8d3b-a16e0fc03731','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meals" VALUES('01a0e7f4-994b-76eb-9ac0-d721e855fb70','Pfannkuchen','pfannkuchen','Mehl, Milch, Eier, Zucker und Salz glatt rühren und 10 Minuten quellen lassen.
In Butter goldbraun ausbacken.',NULL,2,'01a0e7f4-8a4a-7284-a550-c301d98745ff','22a24ca05b19407d8ea5ce01b7918022',NULL,'01a0e7f4-99bf-7362-b953-161627d78c42','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meals" VALUES('01a0e7f4-9952-7024-a21f-c60df788c992','Hähnchen-Reis-Pfanne','haehnchen-reis-pfanne','Reis kochen. Hähnchen scharf anbraten, Gemüse dazugeben.
Den Reis unterheben und alles kurz zusammen braten.',NULL,2,'01a0e7f4-8a4a-7284-a550-c30a8709b408',NULL,NULL,'01a0e7f4-99ca-7016-bbc6-45047b523054','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meals" VALUES('01a0e7f4-9952-7024-a21f-c60df788c992','Tomatensalat','tomatensalat','Tomaten in Scheiben, Zwiebel in feine Ringe schneiden.
Mit Olivenöl, Salz und Pfeffer anmachen.',NULL,2,'01a0e7f4-8a4a-7284-a550-c306cfcc717f','c7035bd8dece4cc3b248a301ed06ea2f',NULL,'01a0e7f4-99cf-754c-b781-d99da821e42f','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meals" VALUES('01a0e7f4-9957-73c7-9e4b-f263774bc144','Ofenkartoffeln mit Kräuterjoghurt','ofenkartoffeln mit kraeuterjoghurt','Kartoffeln vierteln, mit Öl und Salz 40 Minuten bei 200 °C backen.
Joghurt mit Knoblauch verrühren und dazu reichen.',NULL,3,'01a0e7f4-8a4a-7284-a550-c301d98745ff',NULL,NULL,'01a0e7f4-99d7-703c-b8df-4161384dea7c','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meals" VALUES('01a0e7f4-9957-73c7-9e4b-f263774bc144','Tofu-Gemüse-Curry','tofu-gemuese-curry',NULL,NULL,2,'01a0e7f4-8a4a-7284-a550-c30ce14d02ee',NULL,NULL,'01a0e7f4-99dc-75cd-ada1-ac208fdd4faf','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meals" VALUES('01a0e7f4-9942-7185-9914-b342d32c4fdb','Käsebrot','kaesebrot',NULL,NULL,1,'01a0e7f4-8a4a-7284-a550-c301d98745ff',NULL,NULL,'01a0e7f4-99e0-7120-83f3-bb2c8094af3e','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "meals" VALUES('01a0e7f4-9957-73c7-9e4b-f263774bc144','Spaghetti Bolognese','spaghetti bolognese','Zwiebeln und Knoblauch in Olivenöl andünsten.
Hackfleisch krümelig braten, passierte Tomaten dazugeben und 30 Minuten köcheln.
Mit Salz und Pfeffer abschmecken, mit den Spaghetti und Parmesan servieren.','https://de.wikipedia.org/wiki/Sauce_bolognese',4,'01a0e7f4-8a4a-7284-a550-c30253c8d564','745e0498057d4eb290628dfe9b7c3a04','01a0e7f4-99b2-7427-8d3b-a16e0fc03731','01a0e7f4-99e4-728b-8eda-cbb0d23d6949','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
CREATE TABLE one_time_codes (
	kind VARCHAR(10) NOT NULL,
	code_hmac VARCHAR(64) NOT NULL,
	created_by VARCHAR(36),
	target_user_id VARCHAR(36),
	expires_at DATETIME NOT NULL,
	used_at DATETIME,
	used_by VARCHAR(36),
	revoked_at DATETIME,
	tailscale_share_url VARCHAR(500),
	id VARCHAR(36) NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	CONSTRAINT pk_one_time_codes PRIMARY KEY (id),
	CONSTRAINT ck_one_time_codes_kind CHECK (kind IN ('invite', 'reset')),
	CONSTRAINT fk_one_time_codes_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL,
	CONSTRAINT fk_one_time_codes_target_user_id_users FOREIGN KEY(target_user_id) REFERENCES users (id) ON DELETE CASCADE,
	CONSTRAINT fk_one_time_codes_used_by_users FOREIGN KEY(used_by) REFERENCES users (id) ON DELETE SET NULL,
	CONSTRAINT uq_one_time_codes_code_hmac UNIQUE (code_hmac)
);
INSERT INTO "one_time_codes" VALUES('invite','0000000000000000000000000000000000000000000000000000000000000000','01a0e7f4-9942-7185-9914-b342d32c4fdb',NULL,'2026-10-05 12:19:20.444234',NULL,NULL,NULL,NULL,'01a0e7f4-9964-7345-b2a6-92be9607ef2c','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
CREATE TABLE processed_ops (
	user_id VARCHAR(36) NOT NULL,
	op_id VARCHAR(36) NOT NULL,
	list_id VARCHAR(36) NOT NULL,
	applied_at DATETIME NOT NULL,
	CONSTRAINT pk_processed_ops PRIMARY KEY (user_id, op_id),
	CONSTRAINT fk_processed_ops_list_id_shopping_lists FOREIGN KEY(list_id) REFERENCES shopping_lists (id) ON DELETE CASCADE,
	CONSTRAINT fk_processed_ops_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE TABLE products (
	barcode VARCHAR(14) NOT NULL,
	ingredient_id VARCHAR(36) NOT NULL,
	nutrition_basis VARCHAR(2) NOT NULL,
	name VARCHAR(120),
	brand VARCHAR(80),
	quantity_text VARCHAR(40),
	pack_quantity FLOAT,
	pack_unit VARCHAR(10),
	kcal FLOAT,
	protein FLOAT,
	carbs FLOAT,
	sugar FLOAT,
	fat FLOAT,
	source VARCHAR(10) NOT NULL,
	off_last_modified_at DATETIME,
	fetched_at DATETIME,
	user_edited_fields JSON NOT NULL,
	pending_update JSON,
	ignored_off_modified_at DATETIME,
	created_by VARCHAR(36),
	updated_by VARCHAR(36),
	id VARCHAR(36) NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	CONSTRAINT pk_products PRIMARY KEY (id),
	CONSTRAINT ck_products_nutrition_basis CHECK (nutrition_basis IN ('g', 'ml')),
	CONSTRAINT ck_products_source CHECK (source IN ('off', 'manual')),
	CONSTRAINT fk_products_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL,
	CONSTRAINT fk_products_ingredient_id_ingredients FOREIGN KEY(ingredient_id) REFERENCES ingredients (id) ON DELETE RESTRICT,
	CONSTRAINT fk_products_updated_by_users FOREIGN KEY(updated_by) REFERENCES users (id) ON DELETE SET NULL,
	CONSTRAINT uq_products_barcode UNIQUE (barcode)
);
INSERT INTO "products" VALUES('8005516001475','01a0e7f4-9994-74f9-8555-4a4150586165','g','Spaghetti n.5','Barilla','500 g',500.0,'g',359.0,12.0,71.0,3.5,2.0,'manual',NULL,NULL,'["nutrition_basis", "name", "brand", "quantity_text", "pack_quantity", "pack_unit", "nutrients.kcal", "nutrients.protein", "nutrients.carbs", "nutrients.sugar", "nutrients.fat"]',NULL,NULL,'01a0e7f4-994b-76eb-9ac0-d721e855fb70','01a0e7f4-994b-76eb-9ac0-d721e855fb70','01a0e7f4-99a8-71c0-9ad1-900c9d79dd7d','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "products" VALUES('8002331045820','01a0e7f4-9994-74f9-8555-4a4150586165','g','Spaghetti n.12','De Cecco','500 g',500.0,'g',353.0,13.0,70.0,3.5,1.5,'manual',NULL,NULL,'["nutrition_basis", "name", "brand", "quantity_text", "pack_quantity", "pack_unit", "nutrients.kcal", "nutrients.protein", "nutrients.carbs", "nutrients.sugar", "nutrients.fat"]',NULL,NULL,'01a0e7f4-9952-7024-a21f-c60df788c992','01a0e7f4-9952-7024-a21f-c60df788c992','01a0e7f4-99a8-71c0-9ad1-900d179156ca','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "products" VALUES('4028173104529','01a0e7f4-9986-779f-ad93-ea1b6428cf11','ml','Frische Vollmilch 3,5 %','Weihenstephan','1 l',1.0,'l',65.0,3.5,4.8,4.8,3.5,'manual',NULL,NULL,'["nutrition_basis", "name", "brand", "quantity_text", "pack_quantity", "pack_unit", "nutrients.kcal", "nutrients.protein", "nutrients.carbs", "nutrients.sugar", "nutrients.fat"]',NULL,NULL,'01a0e7f4-9952-7024-a21f-c60df788c992','01a0e7f4-9952-7024-a21f-c60df788c992','01a0e7f4-99a8-71c0-9ad1-900e84f23195','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "products" VALUES('4061453007189','01a0e7f4-9989-74dd-a236-202559a213b8','g','Original Irische Butter','Kerrygold','250 g',250.0,'g',741.0,0.6,0.6,0.6,82.0,'manual',NULL,NULL,'["nutrition_basis", "name", "brand", "quantity_text", "pack_quantity", "pack_unit", "nutrients.kcal", "nutrients.protein", "nutrients.carbs", "nutrients.sugar", "nutrients.fat"]',NULL,NULL,'01a0e7f4-9957-73c7-9e4b-f263774bc144','01a0e7f4-9957-73c7-9e4b-f263774bc144','01a0e7f4-99a8-71c0-9ad1-900f4675db88','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "products" VALUES('8004207009356','01a0e7f4-9997-7618-abe0-56163629796d','g','Passata','Mutti','700 g',700.0,'g',36.0,1.6,5.4,4.8,0.2,'manual',NULL,NULL,'["nutrition_basis", "name", "brand", "quantity_text", "pack_quantity", "pack_unit", "nutrients.kcal", "nutrients.protein", "nutrients.carbs", "nutrients.sugar", "nutrients.fat"]',NULL,NULL,'01a0e7f4-994b-76eb-9ac0-d721e855fb70','01a0e7f4-994b-76eb-9ac0-d721e855fb70','01a0e7f4-99a8-71c0-9ad1-9010700cebb4','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "products" VALUES('4017952000633','01a0e7f4-9998-74e2-83e9-6aa9f3f25848','ml','Natives Olivenöl Extra','Bertolli','750 ml',750.0,'ml',828.0,0.0,0.0,0.0,92.0,'manual',NULL,NULL,'["nutrition_basis", "name", "brand", "quantity_text", "pack_quantity", "pack_unit", "nutrients.kcal", "nutrients.protein", "nutrients.carbs", "nutrients.sugar", "nutrients.fat"]',NULL,NULL,'01a0e7f4-9952-7024-a21f-c60df788c992','01a0e7f4-9952-7024-a21f-c60df788c992','01a0e7f4-99a8-71c0-9ad1-9011d4534e38','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
CREATE TABLE session_tokens (
	session_id VARCHAR(36) NOT NULL,
	token_hmac VARCHAR(64) NOT NULL,
	issued_at DATETIME NOT NULL,
	superseded_at DATETIME,
	forked_at DATETIME,
	expires_at DATETIME NOT NULL,
	id VARCHAR(36) NOT NULL,
	CONSTRAINT pk_session_tokens PRIMARY KEY (id),
	CONSTRAINT fk_session_tokens_session_id_sessions FOREIGN KEY(session_id) REFERENCES sessions (id) ON DELETE CASCADE,
	CONSTRAINT uq_session_tokens_token_hmac UNIQUE (token_hmac)
);
CREATE TABLE sessions (
	user_id VARCHAR(36) NOT NULL,
	created_at DATETIME NOT NULL,
	last_used_at DATETIME NOT NULL,
	expires_at DATETIME NOT NULL,
	revoked_at DATETIME,
	user_agent VARCHAR(200),
	parent_session_id VARCHAR(36),
	id VARCHAR(36) NOT NULL,
	CONSTRAINT pk_sessions PRIMARY KEY (id),
	CONSTRAINT fk_sessions_parent_session_id_sessions FOREIGN KEY(parent_session_id) REFERENCES sessions (id) ON DELETE SET NULL,
	CONSTRAINT fk_sessions_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE TABLE shopping_lists (
	owner_id VARCHAR(36) NOT NULL,
	name VARCHAR(60),
	status VARCHAR(10) NOT NULL,
	shared_with_partner BOOLEAN NOT NULL,
	version INTEGER NOT NULL,
	reminder_seed INTEGER NOT NULL,
	shopping_started_at DATETIME,
	finished_at DATETIME,
	id VARCHAR(36) NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	CONSTRAINT pk_shopping_lists PRIMARY KEY (id),
	CONSTRAINT ck_shopping_lists_status CHECK (status IN ('draft', 'shopping', 'done')),
	CONSTRAINT ck_shopping_lists_reminder_seed CHECK (reminder_seed >= 0 AND reminder_seed <= 9999),
	CONSTRAINT ck_shopping_lists_version CHECK (version >= 0),
	CONSTRAINT fk_shopping_lists_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE CASCADE
);
INSERT INTO "shopping_lists" VALUES('01a0e7f4-994b-76eb-9ac0-d721e855fb70','Wochenende','draft',1,0,3,NULL,NULL,'01a0e7f4-99f5-7755-a482-0470341b21ab','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "shopping_lists" VALUES('01a0e7f4-9952-7024-a21f-c60df788c992',NULL,'draft',0,1,7,NULL,NULL,'01a0e7f4-99ff-70f4-a0a6-41f918d3e4fd','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "shopping_lists" VALUES('01a0e7f4-9957-73c7-9e4b-f263774bc144','Grillabend','draft',0,0,12,NULL,NULL,'01a0e7f4-9a01-712d-81a4-5611e0dbe5ba','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "shopping_lists" VALUES('01a0e7f4-994b-76eb-9ac0-d721e855fb70','Wocheneinkauf','shopping',1,1,21,'2026-09-28 11:19:20.444234',NULL,'01a0e7f4-9a05-70ae-844d-2d026b5fa724','2026-09-27 11:19:20.444234','2026-09-28 12:19:22.351676');
INSERT INTO "shopping_lists" VALUES('01a0e7f4-994b-76eb-9ac0-d721e855fb70','Salatabend','done',1,1,4,'2026-09-26 10:19:20.444234','2026-09-26 12:19:20.444234','01a0e7f4-9a8f-75ea-9d47-92612588bfda','2026-09-25 10:19:20.444234','2026-09-28 12:19:22.437601');
INSERT INTO "shopping_lists" VALUES('01a0e7f4-9957-73c7-9e4b-f263774bc144','Vorrat','done',0,1,58,'2026-09-19 11:19:20.444234','2026-09-19 12:19:20.444234','01a0e7f4-9ac6-700f-ba36-fc9a48edd448','2026-09-18 11:19:20.444234','2026-09-28 12:19:22.492618');
CREATE TABLE tags (
	name VARCHAR(30) NOT NULL,
	name_norm VARCHAR(120) NOT NULL,
	id VARCHAR(36) NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	CONSTRAINT pk_tags PRIMARY KEY (id),
	CONSTRAINT uq_tags_name_norm UNIQUE (name_norm)
);
INSERT INTO "tags" VALUES('Pasta','pasta','01a0e7f4-99b7-756d-a8af-6253a2dc5ca1','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "tags" VALUES('Klassiker','klassiker','01a0e7f4-99bc-73ee-b5f2-dce8af8b2493','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "tags" VALUES('Süß','suess','01a0e7f4-99c6-736d-9967-91bbbdbc797f','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "tags" VALUES('Schnell','schnell','01a0e7f4-99c8-7763-8143-d0330d7acd7b','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "tags" VALUES('Vegetarisch','vegetarisch','01a0e7f4-99d3-73e2-9f8b-e3ceaf12afa9','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "tags" VALUES('Salat','salat','01a0e7f4-99d5-715e-aaab-6a77d641534d','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "tags" VALUES('Vegan','vegan','01a0e7f4-99df-74a1-b820-4bf7a6e02b4b','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "tags" VALUES('Frühstück','fruehstueck','01a0e7f4-99e3-7324-82da-4d16c5a9c82c','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
CREATE TABLE users (
	username VARCHAR(30) NOT NULL,
	username_norm VARCHAR(30) NOT NULL,
	display_name VARCHAR(40) NOT NULL,
	display_name_norm VARCHAR(160) NOT NULL,
	password_hash VARCHAR(100) NOT NULL,
	role VARCHAR(10) NOT NULL,
	language VARCHAR(2) NOT NULL,
	is_active BOOLEAN NOT NULL,
	meals_public BOOLEAN NOT NULL,
	lists_public BOOLEAN NOT NULL,
	filter_hidden JSON NOT NULL,
	last_seen_at DATETIME,
	password_changed_at DATETIME,
	password_reset_by VARCHAR(36),
	password_reset_at DATETIME,
	id VARCHAR(36) NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	CONSTRAINT pk_users PRIMARY KEY (id),
	CONSTRAINT ck_users_language CHECK (language IN ('de', 'en')),
	CONSTRAINT ck_users_role CHECK (role IN ('user', 'admin')),
	CONSTRAINT fk_users_password_reset_by_users FOREIGN KEY(password_reset_by) REFERENCES users (id) ON DELETE SET NULL,
	CONSTRAINT uq_users_display_name_norm UNIQUE (display_name_norm),
	CONSTRAINT uq_users_username_norm UNIQUE (username_norm)
);
INSERT INTO "users" VALUES('admin','admin','Admin','admin','not-a-password-hash','admin','de',1,1,1,'{"meals": [], "lists": []}',NULL,NULL,NULL,NULL,'01a0e7f4-9942-7185-9914-b342d32c4fdb','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "users" VALUES('anna','anna','Anna','anna','not-a-password-hash','user','de',1,1,1,'{"meals": [], "lists": []}',NULL,NULL,NULL,NULL,'01a0e7f4-994b-76eb-9ac0-d721e855fb70','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "users" VALUES('ben','ben','Ben','ben','not-a-password-hash','user','en',1,1,1,'{"meals": [], "lists": []}',NULL,NULL,NULL,NULL,'01a0e7f4-9952-7024-a21f-c60df788c992','2026-09-28 12:19:20.444234','2026-09-28 12:19:20.444234');
INSERT INTO "users" VALUES('carl','carl','Carl','carl','not-a-password-hash','user','de',1,0,1,'{"meals": [], "lists": []}',NULL,NULL,NULL,NULL,'01a0e7f4-9957-73c7-9e4b-f263774bc144','2026-09-28 12:19:20.444234','2026-09-28 12:19:22.077772');
CREATE INDEX ix_users_password_reset_by ON users (password_reset_by);
CREATE INDEX ix_admin_events_actor_id ON admin_events (actor_id);
CREATE INDEX ix_admin_events_created_at ON admin_events (created_at);
CREATE INDEX ix_admin_events_target_user_id ON admin_events (target_user_id);
CREATE INDEX ix_couples_addressee_id ON couples (addressee_id);
CREATE INDEX ix_couples_requester_id ON couples (requester_id);
CREATE INDEX ix_one_time_codes_created_by ON one_time_codes (created_by);
CREATE INDEX ix_one_time_codes_target_user_id ON one_time_codes (target_user_id);
CREATE INDEX ix_one_time_codes_used_by ON one_time_codes (used_by);
CREATE INDEX ix_sessions_parent_session_id ON sessions (parent_session_id);
CREATE INDEX ix_sessions_user_id ON sessions (user_id);
CREATE INDEX ix_couple_members_couple_id ON couple_members (couple_id);
CREATE INDEX ix_session_tokens_session_id ON session_tokens (session_id);
CREATE INDEX ix_cuisines_created_by ON cuisines (created_by);
CREATE INDEX ix_ingredients_category_id ON ingredients (category_id);
CREATE INDEX ix_ingredients_created_by ON ingredients (created_by);
CREATE INDEX ix_ingredients_updated_by ON ingredients (updated_by);
CREATE INDEX ix_products_created_by ON products (created_by);
CREATE INDEX ix_products_ingredient_id ON products (ingredient_id);
CREATE INDEX ix_products_updated_by ON products (updated_by);
CREATE INDEX ix_meals_copied_from_meal_id ON meals (copied_from_meal_id);
CREATE INDEX ix_meals_cuisine_id ON meals (cuisine_id);
CREATE INDEX ix_meals_name_norm ON meals (name_norm);
CREATE INDEX ix_meals_owner_id ON meals (owner_id);
CREATE INDEX ix_meal_ingredients_ingredient_id ON meal_ingredients (ingredient_id);
CREATE INDEX ix_meal_ingredients_meal_id ON meal_ingredients (meal_id);
CREATE INDEX ix_meal_tags_tag_id ON meal_tags (tag_id);
CREATE INDEX ix_shopping_lists_owner_id ON shopping_lists (owner_id);
CREATE INDEX ix_list_extra_items_added_by ON list_extra_items (added_by);
CREATE INDEX ix_list_extra_items_category_id ON list_extra_items (category_id);
CREATE INDEX ix_list_extra_items_ingredient_id ON list_extra_items (ingredient_id);
CREATE INDEX ix_list_extra_items_list_id ON list_extra_items (list_id);
CREATE INDEX ix_list_line_states_checked_by ON list_line_states (checked_by);
CREATE INDEX ix_list_meals_added_by ON list_meals (added_by);
CREATE INDEX ix_list_meals_list_id ON list_meals (list_id);
CREATE INDEX ix_list_meals_meal_id ON list_meals (meal_id);
CREATE INDEX ix_list_meals_meal_owner_id_snapshot ON list_meals (meal_owner_id_snapshot);
CREATE UNIQUE INDEX uq_list_meals_list_id_meal_id ON list_meals (list_id, meal_id) WHERE meal_id IS NOT NULL;
CREATE INDEX ix_list_meal_ingredients_category_id_snapshot ON list_meal_ingredients (category_id_snapshot);
CREATE INDEX ix_list_meal_ingredients_ingredient_id ON list_meal_ingredients (ingredient_id);
CREATE INDEX ix_list_meal_ingredients_list_meal_id ON list_meal_ingredients (list_meal_id);
CREATE INDEX ix_processed_ops_list_id ON processed_ops (list_id);
COMMIT;

