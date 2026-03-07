# SK Risk Frontend

This is the SvelteKit analyst console for SK Risk. It consumes the FastAPI JSON API and focuses on evidence-first review rather than generic summary widgets.

## Routes

- `/`: overview metrics, critical skills, feed activity, and VT budget
- `/skills`: registry-wide evidence queue with local filtering
- `/skills/[publisher]/[repo]/[skill_slug]`: latest snapshot dossier for one skill
- `/indicators/[indicator_type]/[indicator_value]`: provider observations, enrichments, and cross-skill reuse
- `/queue/vt`: selective VirusTotal queue status

## Development

```sh
npm install
PUBLIC_SKRISK_API_BASE_URL=http://127.0.0.1:8080 npm run dev
```

If the backend is running on the default local address, the app will query `http://127.0.0.1:8080`.

## Verification

```sh
npm test -- --run
npm run check
npm run build
```

## Design Direction

- data-dense analyst workflow rather than marketing-style UI
- Fira Sans and Fira Code for readable technical content
- accessible light theme with strong focus states and restrained alert colors
- drill-down routes for skills, indicators, and VT queue state
