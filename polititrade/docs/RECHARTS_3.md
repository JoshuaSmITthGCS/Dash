# Recharts 3 adoption plan

Recharts 2 was removed because the application does not import it. This avoids shipping and
maintaining an unused, unsupported dependency.

When the first chart is designed:

1. Add current Recharts 3 and a `react-is` version matching React.
2. Build a single accessible chart wrapper with a textual summary, legend, keyboard-readable
   tooltip content, responsive container sizing, and the existing semantic color tokens.
3. Add component tests for empty, partial, and full datasets plus a production bundle check.
4. Migrate one view at a time; do not mix Recharts 2 and 3 APIs.
