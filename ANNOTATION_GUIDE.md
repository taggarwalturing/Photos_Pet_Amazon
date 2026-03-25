# Annotation Guide — Step by Step

## 1. Login

- Open **https://photo-pets.turing.com/**
- Enter your **Turing email** and the **password** shared with you.

## 2. Dashboard Overview

After login you'll see your dashboard with:
- **Assigned** — total images assigned to you
- **Annotated** — images you've completed
- **Remaining** — images left to annotate

Use the filter buttons (**All / Pending / Completed**) to view images by status.

## 3. Annotate an Image

1. Click any **Pending** image to open it.
2. You'll see the image on the left and **6 categories** on the right.
3. For each category, **select one option** that best describes the image:

### Category 1 — Lighting Variation
*What lighting condition is present in the image?*

| Label | Definition |
|-------|-----------|
| Dusk-dawn lighting | Golden/orange warm tones, sunset or sunrise lighting |
| Harsh outdoor sunlight with shadows | Bright direct sun creating strong, hard shadows and high contrast |
| Low light conditions | Dark, dim, grainy image with poor visibility |
| Well-lit conditions (typical) | Even, balanced lighting with no extreme shadows or highlights |
| None of the Above | Doesn't match any of the above |

### Category 2 — Angle & Perspective Variation
*What is the camera's position relative to the pet?*

| Label | Definition |
|-------|-----------|
| Front-facing at eye level (typical) | Camera is at the pet's eye height, shooting straight on |
| Ground-level view | Camera is placed on or near the ground, shooting upward at the pet |
| No head showing | The pet's head is not visible in the frame |
| Partial view (head only) | Only the pet's head/face is visible (close-up) |
| Top-down view | Camera is directly above the pet, looking straight down |
| None of the Above | Doesn't match any of the above |

### Category 3 — Environmental Context Variation
*Where is the pet located?*

| Label | Definition |
|-------|-----------|
| In car-carrier | Pet is inside a car or pet carrier/crate |
| Indoor setting (typical) | Inside a building — furniture, walls, floors visible |
| Outdoor dirt road | Outside on a dirt path, trail, or unpaved surface |
| Snow environment | Snow is visible in the scene |
| Vet clinic | Veterinary clinic setting (exam table, medical equipment) |
| Yard with a complex background | Outdoor yard with a busy, cluttered background |
| None of the Above | Doesn't match any of the above |

### Category 4 — Occlusion & Partial Visibility
*Is anything blocking or hiding part of the pet?*

| Label | Definition |
|-------|-----------|
| Behind furniture (face only) | Pet is behind furniture with only its face peeking out |
| Full-body, unobstructed (typical) | The entire pet body is clearly visible, nothing blocking it |
| Partially hidden under a blanket | Part of the pet is covered or hidden under a blanket |
| Peeking out of box-carrier | Pet is peeking out from inside a box or carrier |
| Toy obscuring part of body | A toy is covering or blocking part of the pet's body |
| Partial Visible Body | Only part of the pet's body is visible in the frame (e.g., cropped or cut off) |
| None of the Above | Doesn't match any of the above |

### Category 5 — Activity & Motion
*What is the pet doing?*

| Label | Definition |
|-------|-----------|
| Eating-drinking | Pet is eating food or drinking water |
| Jumping to catch toy | Pet is mid-air or leaping to catch a toy |
| Playing with another pet | Pet is actively playing or interacting with another animal |
| Running with motion blur | Pet is running and there is visible motion blur |
| Sitting still-posed (typical) | Pet is sitting calmly, still, or posing for the camera |
| Sleeping-curled up | Pet is sleeping, eyes closed, or curled up resting |
| Standing still-posed | Pet is standing still, alert, or posed (not sitting or lying down) |
| None of the Above | Doesn't match any of the above |

### Category 6 — Multi-Pet Disambiguation
*How many pets are in the image?*

| Label | Definition |
|-------|-----------|
| Pet with breed lookalike | One pet alongside a lookalike toy or stuffed animal of the same breed |
| Single pet (typical) | Only one pet is visible in the image |
| Three pets of same breed | Three pets of the same breed are present |
| Two similar-looking pets together | Two pets that look alike (same breed/color) are in the frame |
| None of the Above | Doesn't match any of the above |

---

4. Some images may have an **AI suggestion** (highlighted in blue). Verify it — **accept** if correct or **change** if not.
5. Select **"None of the Above"** if no option fits for that category.

## 4. Save & Move On

- Click **Save** to save your selections.
- Click **Save & Next** to save and jump to the next pending image.
- Use **← Prev / Next →** buttons to navigate between images.

## 5. Blur Tool (Privacy)

Some images may contain **human faces** that need to be blurred for privacy. Use the blur tool to handle this:

### When to Blur
- If a **human face** is visible in the image, you **must blur it** before saving.

### How to Blur
1. Click the **Blur** button on the toolbar.
2. **Draw a rectangle** over the human face you want to blur.
3. The selected area will be blurred and saved automatically.
4. Repeat for each human face in the image.

### When to Unblur
- If the image has **no human face** but a blur is already applied (e.g., auto-blur picked up something incorrectly), **remove the blur**.
- If a blur was **mistakenly applied on the animal/pet**, **remove it** — only human faces should be blurred, never the pet.

### How to Unblur
1. Click the **Unblur** button on the toolbar.
2. The incorrectly applied blur will be removed.

> **Rule of thumb**: Blur = human faces only. Never blur the pet. Remove any blur that doesn't cover a human face.

## 6. Mark Improper Images

If an image is **unclear, corrupt, or not a pet photo**, click the **⚠ Mark Improper** button instead of annotating it.

## 7. Mark Duplicates

If you notice **duplicate images**:
1. Go back to the dashboard.
2. Select the duplicate images using the checkboxes (the **first selected** image becomes the parent).
3. Click **Mark as Duplicate**.

## 8. Rotate for Better View

Use the **rotate button (↻)** on the image to rotate it for better judgment. This is UI-only and does not affect the actual image.

## 9. Important Notes

- **Once saved**, an image is locked and cannot be edited unless a reviewer sends it back.
- You can only see and annotate images **assigned to you**.
- All 6 categories **must** be filled before saving.
- Your progress is tracked automatically — no need to log time.
