# Shot list: 80 staged photos

Owner: Carlos. Draft Oct 26. Phase 0 step 2. Team to review before shooting.

## Rules for every photo

- Consenting teammates only. No bystanders, no real neighbors, no real cars you do not have permission to shoot.
- Fake data only, from the reference list below. Nothing real, even "harmless" real data.
- Shoot HEIC or JPEG, not ProRAW (DNG fails the upload limit and Pillow, gotcha 27).
- Images go to team private storage under `eval/data/`, never git. File name is the image id, for example `s01.jpg`.
- Each photo gets one row in `manifest.jsonl` (`source: staged`, `license: team staged, fake data`) and one label file. `categories` in the manifest comes from the Categories column.
- Vary light, angle and distance across a category. Do not shoot ten copies of the same setup.

## Fake data reference

Use these so labels stay consistent. All are obviously fake by design.

| Item | Value |
|---|---|
| Name | Jordan Example, Sam Placeholder |
| Address | 1427 Maple Test St, Faketown (house number printed large, street sign printed on paper and taped to a pole or wall) |
| Phone | 555 0142 (555 01xx range is reserved for fiction) |
| Email | jordan@example.com |
| Card with a valid checksum (trips the floor rule) | 4242 4242 4242 4242 |
| Card with an invalid checksum (tests the SAM class, not the floor rule) | 4000 1234 5678 9011 |
| SSN | 123-45-6789 |
| Wi-Fi / passwords | TestNet-Kestrel42, Plum-Ferry-88!, Spring2026! |
| API key | FAKEKEY_9f3kd82ksl20x (do not use a real vendor prefix) |
| ID cards, passport, license, prescription, lab results | Printed mocks you make yourself. A teammate's face on a mock ID is fine with consent. |

## Flags

- `B`: in the Oct 27 bake off (20 images, all dev split).
- `3`: labeled for all three destinations (30 images).
- `dev` or `test`: split. **The test split is frozen when this list is approved, before any image is scored.** Prompt and threshold tuning uses dev only.

## The 80

| ID | Scene | Fake data | Categories | Flags |
|---|---|---|---|---|
| s01 | Wi-Fi password on a sticky note stuck to a router | TestNet-Kestrel42 | credential | B dev |
| s02 | Whiteboard of 8 meeting note lines, one is a password | Plum-Ferry-88! | credential | B 3 dev |
| s03 | Laptop terminal showing an .env file | FAKEKEY_ value | credential | test |
| s04 | Printed 2FA recovery codes on a desk | 8 random fake codes | credential | dev |
| s05 | Password manager window open on a monitor | fake vault entries | credential | test |
| s06 | Notebook page: shopping list with one login line | Spring2026! | credential | dev |
| s07 | Phone lock screen with a 6 digit 2FA code notification | fake code | credential | test |
| s08 | Sticky note on a monitor bezel | admin / Spring2026! | credential | B dev |
| s09 | Chat app screen where someone pastes a token | FAKEKEY_ value | credential | test |
| s10 | Router label sticker with default Wi-Fi password | fake sticker | credential | dev |
| s11 | Card lying on a desk | 4242 card | payment | B dev |
| s12 | Card held in a hand, angled | 4000 card, invalid checksum | payment | test |
| s13 | Checkout page on a laptop with card fields filled | 4242 card | payment | dev |
| s14 | Paper bank statement | fake account and IBAN | payment, personal_account | test |
| s15 | Phone banking screen with balance and account number | fake account | payment | dev |
| s16 | Invoice with payment details | fake IBAN | payment | test |
| s17 | Mock driver license on a desk | fake license number, teammate face | government_id, face | B dev |
| s18 | Mock passport data page | fake passport number | government_id | test |
| s19 | Mock student ID on a lanyard worn by a teammate | fake ID number | government_id, face | 3 dev |
| s20 | Paper form with an SSN written in | 123-45-6789 | government_id | test |
| s21 | Mock ID card half covered by papers | fake number | government_id | dev |
| s22 | Mock visa or permit form | fake numbers | government_id | test |
| s23 | Email inbox on a laptop | fake senders, subjects | personal_account | B dev |
| s24 | Order confirmation on a phone with name and address | Jordan Example, 1427 Maple Test St | personal_account, home_location | test |
| s25 | Shipping label on a box | Jordan Example, address | personal_account, home_location | dev |
| s26 | Mock boarding pass | fake name, booking code | personal_account | test |
| s27 | Chat app screen with usernames and message text | fake users | personal_account | dev |
| s28 | Login page with the username filled in | jordan@example.com | personal_account | test |
| s29 | Mug with a phone number printed on it | 555 0142 | contact_info | B dev |
| s30 | Business card on a desk | name, email, phone | contact_info | test |
| s31 | Fridge note with a phone number | 555 0142 | contact_info | dev |
| s32 | Whiteboard contact list | names, phones | contact_info | test |
| s33 | Laptop email signature | email, phone | contact_info | dev |
| s34 | House number and street sign in one frame (multi clue) | 1427 plus Maple Test St sign | home_location | B 3 dev |
| s35 | Same idea, number small and far away | 1427 plus sign | home_location | test |
| s36 | Mail on a doorstep with an address, no street sign | address on envelope | home_location | B dev |
| s37 | Package label on a porch plus a house number | label, 1427 | home_location | test |
| s38 | Map screen with a pin labeled "Home" | fake map pin | home_location | dev |
| s39 | House number alone, no sign or label (should not combine) | 1427 only | home_location | test |
| s40 | Street sign alone, no number (near miss) | Maple Test St only | home_location | dev |
| s41 | Apartment door number plus a building name sign | fake building | home_location | test |
| s42 | Teammate selfie, face fills the frame | none | face | B 3 dev |
| s43 | Group photo of three teammates | none | face | 3 test |
| s44 | Teammate in the background, subject in the foreground | none | face | B 3 dev |
| s45 | Video call screenshot showing several faces | teammates | face | 3 dev |
| s46 | Face reflected in a window or a dark monitor | none | face | 3 dev |
| s47 | Teammate in sunglasses and a mask | none | face | test |
| s48 | Printed photo of a teammate pinned on a wall | none | face | dev |
| s49 | Wide shot, faces small and far away | none | face | test |
| s50 | A teammate's car, plate readable | fake or real plate of the consenting owner | license_plate | B 3 dev |
| s51 | Street shot, own car plate at an angle | same | license_plate | 3 test |
| s52 | Parking lot with two consenting teammates' cars | plates | license_plate | 3 dev |
| s53 | Plate partly cut off at the frame edge | plate | license_plate | test |
| s54 | Dashboard on a monitor with fake revenue | fake figures | internal_data | B 3 dev |
| s55 | Customer table on a laptop | fake names, accounts | internal_data, personal_account | 3 test |
| s56 | Roadmap slide on a screen | fake product plans | internal_data | B 3 dev |
| s57 | Sprint whiteboard with fake client codenames | codenames | internal_data | 3 test |
| s58 | Printed "CONFIDENTIAL" org chart | fake names | internal_data | 3 dev |
| s59 | Code editor showing internal fake hostnames | fake hosts | internal_data | test |
| s60 | Pill bottle with a fake prescription label | fake name, drug | other_sensitive | B dev |
| s61 | Fake lab results printout | fake values | other_sensitive | test |
| s62 | Calendar showing a trip, away from home dates | fake dates | other_sensitive | B dev |
| s63 | Health app screen on a phone | fake data | other_sensitive | test |
| s64 | Teammate wearing a name badge in front of a building sign (multi clue) | fake employer | other_sensitive, face | B 3 dev |
| s65 | Face plus a name badge | fake name | face, other_sensitive | test |
| s66 | License plate plus house number in one frame (multi clue) | plate, 1427 | license_plate, home_location | B dev |
| s67 | Vacation calendar plus mail with the home address (multi clue) | fake dates, address | other_sensitive, home_location | test |
| s68 | Home office desk: monitor with email, sticky password, mug with phone, teammate in frame | mixed | credential, contact_info, personal_account, face | 3 dev |
| s69 | Meeting room whiteboard: agenda, one credential, names | mixed | credential, internal_data | 3 test |
| s70 | Kitchen: fridge notes, package label, teammate | mixed | contact_info, home_location, face | B 3 dev |
| s71 | Porch: house number, package label, car plate in driveway | mixed | home_location, license_plate | 3 test |
| s72 | Dorm desk: laptop chat, mock ID, sticky | mixed | personal_account, government_id, credential | B 3 dev |
| s73 | Cafe table: phone banking, card, teammate | mixed | payment, personal_account, face | 3 test |
| s74 | Network closet: router label, Wi-Fi sticker, dashboard | mixed | credential, internal_data | 3 dev |
| s75 | Car interior: parking permit, phone navigation to home, teammate | mixed | home_location, face, other_sensitive | 3 test |
| s76 | Lab bench: monitor with internal data, name badge, whiteboard | mixed | internal_data, other_sensitive | 3 dev |
| s77 | Hallway bulletin board: flyers with phones, one sticky with a code | mixed | contact_info, credential | 3 test |
| s78 | Living room: TV video call, mail on a table | mixed | face, home_location | 3 dev |
| s79 | Street scene: sign, house number, a plate, teammates passing by | mixed | home_location, license_plate, face | 3 test |
| s80 | Flat lay: mock passport, boarding pass, card, phone lock screen | mixed | government_id, payment, personal_account | 3 dev |

## Hard negatives (20, proposed, not in the 80)

These look sensitive and are not. A mask on any of them counts as a hard negative false positive, so each should be a scene a sensible reviewer would leave alone. The docs do not say where the 20 come from; this is my proposal and the team needs to approve it.

Ideas: a whiteboard of lunch orders; a street sign with no house number; a monitor showing a wallpaper or a public website; a code editor with no secrets; a printed lorem ipsum document; a sticky note that says "buy milk"; a shop front with a company logo; a bookshelf; an empty desk; a mug with a slogan; a car with the plate covered by a blank, unreadable frame (no real plate); a map with no pin; a boarding pass shaped prop with only "SAMPLE" text; a team poster of a public figure.

## Counts

Run `uv run python eval/check_shot_list.py` to check these against the table: 80 rows, 20 `B` all in dev, 30 `3`, every category in the judge schema present.
