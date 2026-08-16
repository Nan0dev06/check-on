/* Self-hosted fonts.
 *
 * The handoff says "Fonts are Google Fonts — self-host them in production", so
 * they are bundled rather than fetched. That also means the app renders the
 * intended type on a first paint with no network, which matters more here than
 * usual: the fallback stack changes the elder view's line count, and the fit
 * requirement is measured in lines.
 *
 * Only the weights DESIGN_SYSTEM.md §3 names are imported.
 */
import '@fontsource/archivo/400.css'
import '@fontsource/archivo/500.css'
import '@fontsource/archivo/600.css'
import '@fontsource/archivo/700.css'
import '@fontsource/caveat/600.css'
import '@fontsource/ibm-plex-mono/400.css'
import '@fontsource/ibm-plex-mono/500.css'
import '@fontsource/newsreader/400.css'
