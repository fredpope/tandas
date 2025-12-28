# Security Guidelines

Tandas handles configuration files (e.g., `.tandas/config.yaml`, `.tandas/env.example`) that may reference API keys for AI providers. Follow these practices to keep credentials safe:

1. **Never commit real secrets**: Keep API keys in shell environment variables or local files that are ignored by Git. `td quickstart` auto-adds `.tandas/env.*` and `.env*` patterns to `.gitignore`, but double-check before committing.
2. **Use placeholders**: The generated `.tandas/config.yaml` references `${ANTHROPIC_API_KEY}`-style placeholders so you don’t store actual secrets in Git. Export the real values in your shell (`source .tandas/env.example`) instead.
3. **Rotate and prune**: If credentials are ever exposed, rotate them immediately. Remove sensitive files from history (e.g., `git filter-repo`) and regenerate keys.
4. **Limit scope and permissions**: Use provider-specific service accounts or API keys with the minimum required privileges.
5. **Report issues**: If you discover a vulnerability or have questions, open an issue or contact fredpope@example.com.

By following these guidelines, teams can safely use Tandas/Td while keeping provider secrets out of the repository.
