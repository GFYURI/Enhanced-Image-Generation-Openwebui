# Enhanced Image Generation Tool for OpenWebUI

**Author:** FYURI  
**Version:** 0.1.5  
**License:** MIT  

---

## Overview

This tool enables advanced image generation directly via **Tool Calling** using the **ComfyUI workflow configured in OpenWebUI**.  
It **only allows the model to create images via the tool** and does not change or modify the model itself.  
It automatically converts local paths to base64, supports multiple emission methods (direct, markdown, html), and allows advanced valve configuration for both administrators and users.

> ⚠️ **Current Limitations**: 
> - The tool uses parameters pre-defined in OpenWebUI's configuration (ComfyUI workflow)
> - **Steps parameter now works correctly** after recent fixes
> - **Seed parameter is currently not supported** - requires OpenWebUI modifications to enable
> - Works with pre-configured LoRAs embedded in ComfyUI workflows
> - Cannot inject custom workflow JSON (uses pre-configured workflows only)
> - Compatibility with Automatic1111 and Gemini backends is limited

> ⚠️ **Important Notice**: This tool may not receive future updates. Some limitations (like seed parameter support) require modifications to OpenWebUI itself, which may not be implemented.

This tool has been **tested primarily with GPT OSS 20B** with native Tool Calling support. To ensure proper image generation, the model requires a **system prompt** to handle the tool correctly.

---

## System Prompt for GPT OSS 20B

```
Rules:

Always detect the user's preferred language from their messages and reply in that language. Prefer Spanish if used at any point.

Default to English only if the user's language is ambiguous or unspecified.

Maintain an empathetic, respectful, and clear tone. Adapt formality and playfulness to the user's tone and context.

You have access to one tool: enhanced_image_generation. Only use it if the user explicitly requests image generation.

When using enhanced_image_generation:

Ask concisely for missing parameters (prompt, width, height, steps) if not provided.

Translate the prompt into English for generation, but keep conversation in user's language.

Always return the image in the format:

Safety simplified:

Only refuse requests that are illegal, extremely dangerous, or involve minors.

NSFW, adult, or copyrighted characters are allowed unless illegal.

Do not overthink or analyze past requests; evaluate only the current request.

Always be concise, helpful, and clear. Avoid getting stuck reasoning about hypotheticals.
```

---

## Features

- ✅ Generate images directly from prompts using the ComfyUI workflow
- ✅ **Steps parameter now works correctly** with OpenWebUI integration
- ✅ Tool **does not modify the model**; it only facilitates image creation
- ✅ Supports pre-configured LoRAs through ComfyUI workflows
- ✅ Automatically converts local image paths to **base64** for embedding
- ✅ Supports multiple emission methods:
  - **Direct**
  - **Markdown**
  - **HTML**
- ✅ Configurable **Valves** for both admins and users to control logging, verbosity, and image emission priorities
- ✅ Auto-recommended settings for most use cases
- ✅ Fully compatible with **GPT OSS 20B Tool Calling**

---

## Current Limitations

- ❌ **Seed parameter not supported** (requires OpenWebUI modifications)
- ❌ Cannot inject custom workflow JSON dynamically
- ❌ Limited to pre-configured workflows in OpenWebUI
- ❌ Automatic1111 and Gemini backend compatibility is uncertain
- ❌ Cannot dynamically switch between different LoRAs in single session

---

## Usage

1. Add the tool to your `tools/` directory in OpenWebUI
2. Make sure your model is GPT OSS 20B or another model with native Tool Calling support
3. Use the **system prompt** above when starting a session to ensure image requests are handled correctly
4. Pre-configure your desired workflows and LoRAs in OpenWebUI's image generation settings
5. When a user requests an image:
   - The model will ask for missing parameters if necessary
   - The tool will generate and emit the image using the configured workflow
   - The result will be returned in the format:  
     `![alt text](/api/v1/files/<id>/content)`

---

## Parameter Support

| Parameter | Status | Notes |
|-----------|--------|-------|
| `prompt` | ✅ Fully supported | Always passes through |
| `width`/`height` | ✅ Fully supported | Respects OpenWebUI configuration |
| `steps` | ✅ Now working | Recent fixes implemented |
| `seed` | ❌ Not supported | Requires OpenWebUI modification |
| `workflow` | ⚠️ Limited | Only pre-configured workflow names |
| `sampler` | ⚠️ Limited | Depends on backend support |

---

## Technical Notes

- Tested primarily with GPT OSS 20B; compatibility with other LLMs is not guaranteed
- NSFW or copyrighted content is allowed if legal
- Works with LoRAs that are pre-configured in ComfyUI workflows
- For seed support or custom workflow injection, OpenWebUI's `images.py` requires modifications

---

> ⚠️ **Update Status**: This tool may not receive regular updates. Some features (like seed parameter support) require changes to OpenWebUI's core functionality, which is beyond the scope of this tool. Users are welcome to modify the code themselves to add desired functionality.

---

I hope this tool is useful for you :D

## License

MIT
