# ComfyUI screenshots (submission requirement)

Drop two screenshots here, e.g. `run-1.png` and `run-2.png`:

- Same reference product image loaded into the `LoadImage` node
- Same text prompt in the positive `CLIPTextEncode` node
- Two separate **Queue Prompt** runs (different seeds — leave `seed` on
  `randomize`, or just run it twice) showing the two different generated
  results side by side with the ComfyUI graph visible in frame

## How to produce them

1. Open your Colab tunnel URL (`https://*.trycloudflare.com`) in a browser — this loads the ComfyUI web UI directly.
2. Use the menu (top-left, or right-click canvas > **Load**) to load `comfyui/workflow_api.json`.
   - Note: this file is in the API/prompt format. If your ComfyUI build's UI loader expects the UI-native workflow format instead, it's simplest to rebuild the same graph by hand in the UI (Add Node > loaders > Load Checkpoint, Add Node > loaders > Load Image, two CLIP Text Encode nodes, KSampler with `denoise` ~0.55, VAE Decode, Upscale Model Loader + Upscale Image (using Model), Save Image) and wire it exactly as described in the main README, then use **Workflow > Export (API)** to get an equivalent `workflow_api.json` to replace the one in this repo.
3. Upload your product reference image into the `LoadImage` node.
4. Type your prompt into the positive `CLIPTextEncode` node.
5. Click **Queue Prompt**, wait for the result, screenshot the full browser window (graph + result image visible).
6. Click **Queue Prompt** again (same inputs, new random seed) for a second, different result. Screenshot again.
7. Save both images into this folder and reference them from the main README.
