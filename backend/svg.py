import textwrap
from html import escape


def lines(text, width):
    return textwrap.wrap(text, width=width, break_long_words=True, replace_whitespace=True) or ['']


def render_svg(brief, copy, design):
    bg, fg, accent = (design[k] for k in ('background', 'foreground', 'accent'))
    headline = lines(copy['headline'], 19)
    supporting = lines(copy['supporting'], 51)
    # Fit the full approved content, never silently truncate it.
    size = min(70, 300 / (len(headline)*1.22), 672 / max(map(len, headline)))
    body_size = min(23, 190 / (len(supporting)*1.22), 672 / max(map(len, supporting)))
    def block(items, y, font_size, color, weight=400):
        return ''.join(f'<text x="64" y="{y+i*font_size*1.22:.1f}" fill="{color}" font-size="{font_size:.1f}" font-weight="{weight}">{escape(line)}</text>' for i, line in enumerate(items))
    motif = {
        'orbit': f'<circle cx="640" cy="210" r="190" fill="none" stroke="{accent}" stroke-width="2"/><circle cx="640" cy="210" r="135" fill="none" stroke="{accent}" stroke-width="35"/><circle cx="494" cy="130" r="24" fill="{accent}"/>',
        'steps': ''.join(f'<rect x="{440+i*55}" y="{80+i*38}" width="45" height="220" fill="{accent}"/>' for i in range(6)),
        'sunburst': f'<circle cx="650" cy="200" r="155" fill="{accent}"/><circle cx="650" cy="200" r="95" fill="{bg}"/>'}[design['motif']]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="800" height="1100" viewBox="0 0 800 1100" role="img" aria-label="{escape(brief['title'], quote=True)}">
<title>{escape(brief['title'])}</title><rect width="800" height="1100" fill="{bg}"/>
<g font-family="Arial, Helvetica, sans-serif">{motif}
<text x="64" y="90" fill="{accent}" font-size="15" letter-spacing="4">AN INVITATION TO SOMETHING NEW</text>
{block(headline, 405, size, fg, 700)}
<path d="M64 750H736" stroke="{accent}"/>
{block(supporting, 795, body_size, fg)}
<rect x="64" y="1010" width="672" height="56" rx="28" fill="{accent}"/>
<text x="400" y="1046" text-anchor="middle" fill="{bg}" font-size="{min(23, 640/max(len(copy['cta']),1)):.1f}" font-weight="700">{escape(copy['cta'])}</text>
</g></svg>'''


def contrast(a, b):
    def luminance(color):
        values = [int(color[i:i+2], 16)/255 for i in (1, 3, 5)]
        values = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in values]
        return sum(v*w for v, w in zip(values, (.2126, .7152, .0722)))
    x, y = sorted((luminance(a), luminance(b)))
    return (y+.05)/(x+.05)


def layout_metrics(copy, design):
    return {'text_contrast': round(contrast(design['background'], design['foreground']), 2),
            'cta_contrast': round(contrast(design['background'], design['accent']), 2),
            'headline_lines': len(lines(copy['headline'], 19)), 'supporting_lines': len(lines(copy['supporting'], 51)),
            'approved_copy_preserved': True}
