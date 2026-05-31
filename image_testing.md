# Image Integration Testing Playbook

## Test Agent Rules (from integration_playbook_expert_v2)

### Image Handling Rules
- Always use base64-encoded images for all tests and requests.
- Accepted formats: **JPEG, PNG, WEBP only**.
- Do not use SVG, BMP, HEIC, or other formats.
- Do not upload blank, solid-color, or uniform-variance images.
- Every image must contain real visual features — objects, edges, textures, shadows.
- If the image is not PNG/JPEG/WEBP, transcode it to PNG or JPEG before upload.
- Always re-detect and update the MIME after transformations.
- If the image is animated (GIF, APNG, WEBP animation), extract the first frame only.
- Resize large images to reasonable bounds (avoid oversized payloads).

## Test Coverage for `/api/chat/stream` with images

1. **Single image + text** — POST with `images: ["data:image/jpeg;base64,..."]` and `content: "What hazards do you see?"`. Expect SSE stream → `sources` event → `done` event with `final_text` describing image features.
2. **Multiple images** — up to 3 images per request, all forwarded to Claude vision.
3. **Oversized image** — single image > 5 MB → expect 413 (Payload Too Large) or 400 error.
4. **Bad MIME (e.g. SVG, GIF)** — expect 400.
5. **Image without text** — accept (use placeholder query).
6. **Visual + RAG mash-up** — retrieval still runs, citations still attached when relevant docs exist.

## Test images
- Use real EHS-themed photos (PPE, drum labels, hazard signs).
- Generate with Pillow for synthetic test cases (e.g. red circle on white = visual feature present).
