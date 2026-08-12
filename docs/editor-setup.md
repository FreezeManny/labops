# Editor setup

labops publishes a JSON Schema for the config file. Point your editor at it and
you get completion, hover documentation and inline validation while you write —
the same descriptions you see in this reference, without leaving the file.

## The schema

```
https://freezemanny.github.io/labops/labops.schema.json
```

It is generated from the same models that validate your config at run time, so
it cannot describe a key labops does not actually accept.

## Turn it on

Add one comment to the top of your `homelab.yml`:

```yaml
# yaml-language-server: $schema=https://freezemanny.github.io/labops/labops.schema.json

settings:
  default_creds:
    username: root
    ssh_key_path: ~/.ssh/id_ed25519
```

That line is understood by the [YAML Language
Server](https://github.com/redhat-developer/yaml-language-server), which is what
powers YAML support in VS Code, Neovim, Helix, JetBrains IDEs and anything else
speaking LSP. No editor-specific configuration is needed.

=== "VS Code"

    Install the [YAML
    extension](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml)
    and the comment above is enough.

    To apply it to every config without the comment, add to `settings.json`:

    ```json
    {
      "yaml.schemas": {
        "https://freezemanny.github.io/labops/labops.schema.json": [
          "homelab.yml",
          "homelab.yaml"
        ]
      }
    }
    ```

=== "Neovim"

    With `yamlls` configured through `nvim-lspconfig`, the comment is enough. To
    map it by filename instead:

    ```lua
    require("lspconfig").yamlls.setup {
      settings = {
        yaml = {
          schemas = {
            ["https://freezemanny.github.io/labops/labops.schema.json"] =
              { "homelab.yml", "homelab.yaml" },
          },
        },
      },
    }
    ```

=== "JetBrains"

    **Settings → Languages & Frameworks → Schemas and DTDs → JSON Schema
    Mappings**. Add the URL above and map it to `homelab.yml`.

=== "Offline"

    The schema is not committed to the repository — it is generated at build
    time. To produce a local copy from a checkout:

    ```bash
    uv run python docs/gen_docs.py   # writes docs/labops.schema.json
    ```

    Then reference it by relative path:

    ```yaml
    # yaml-language-server: $schema=./labops.schema.json
    ```

## What you get

- **Completion** for every key, at every level of the tree.
- **Hover documentation** — the description from the
  [configuration reference](configuration/index.md), inline.
- **Unknown keys flagged as you type.** The schema sets
  `additionalProperties: false` everywhere, matching labops' own rule that a key
  it does not recognise is an error rather than something ignored. A typo shows
  up immediately instead of at the next `labops validate`.
- **Type and format checks** — IP addresses, ports, enum values like
  `os: debain`.

## What it does not replace

The schema checks shape. It cannot check the rules that involve more than one
field — that credentials set exactly one auth method, that exactly one access
list is the default, that vmids do not collide, that a node's name is a legal DNS
label once `settings.dns` is configured, that a referenced template file exists.

`labops validate` checks all of those. Keep running it.
