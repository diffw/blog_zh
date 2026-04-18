# Manual Test Checklist

## Goal

Verify the debounce-based auto-publish flow against the real Obsidian source directory.

## Preconditions

- Dependencies installed:
  `python3 -m pip install --user -r requirements.txt`
- Git remote is reachable from this machine.
- The source directory exists:
  `/Users/diffwang/Library/Mobile Documents/iCloud~md~obsidian/Documents/notes/diff-blog`

## Test 1: Ignore `template.md`

1. Edit `template.md`.
2. Wait more than the debounce window.
3. Confirm that no publish commit is created for `content/posts`.

Expected:

- No sync runs because `template.md` is ignored.

## Test 2: Draft filtering

1. Create a temporary article in `diff-blog` with:
   `draft: true`
2. Wait past the debounce window.

Expected:

- The file does not appear in `content/posts/`.
- No publish commit includes that file.

Then:

1. Change the same article to `draft: false`.
2. Wait past the debounce window.

Expected:

- The article appears in `content/posts/`.
- A publish commit is created.

## Test 3: Published article update

1. Pick an existing `draft: false` article.
2. Change one sentence.
3. Stop editing and wait past the debounce window.

Expected:

- The corresponding file in `content/posts/` is updated.
- A publish commit is created after the quiet period, not immediately.

## Test 4: Delete or unpublish

1. Delete a published article from `diff-blog`, or change it to `draft: true`.
2. Wait past the debounce window.

Expected:

- The corresponding file is removed from `content/posts/`.
- A publish commit is created.

## Test 5: Debounce behavior

1. Start editing a published article.
2. Make another edit before the debounce window expires.
3. Repeat a few times.

Expected:

- No publish occurs while edits continue inside the debounce window.
- Only one publish occurs after the final edit has been quiet for the full debounce period.

## Test 6: Other repo changes stay untouched

1. Make an unrelated local change outside `content/posts/`, for example in `README.md`.
2. Edit a published article in `diff-blog`.
3. Wait past the debounce window.

Expected:

- The auto-publish commit only includes `content/posts/`.
- The unrelated local change remains in the working tree.
