"""Reusable browser assertions for Friendly's responsive-layout contract.

Pass an authenticated Playwright page when checking protected routes. This file
does not create accounts or alter application data, so each test suite controls
its own disposable fixture.
"""

STANDARD_VIEWPORT_WIDTHS = (320, 360, 375, 390, 412, 480, 768, 1024, 1280, 1440)


def verify_responsive_layout(page, base_url, routes, widths=STANDARD_VIEWPORT_WIDTHS):
    """Assert document fit, visible targets, and unclipped authenticated links."""
    results = []
    for route, ready_selector in routes:
        page.goto(f"{base_url}{route}", wait_until="domcontentloaded")
        page.locator(ready_selector).wait_for(state="visible")
        for width in widths:
            page.set_viewport_size({"width": width, "height": 900})
            page.wait_for_timeout(40)
            measurement = page.evaluate(
                """() => ({
                    scrollWidth: document.documentElement.scrollWidth,
                    clientWidth: document.documentElement.clientWidth,
                    clippedNavLinks: [...document.querySelectorAll('.app-nav a')]
                        .filter(link => link.scrollWidth > link.clientWidth).length,
                    controlsOutsideViewport: [...document.querySelectorAll('input, select, textarea, button, a')]
                        .filter(element => {
                            const rect = element.getBoundingClientRect();
                            const style = getComputedStyle(element);
                            return style.display !== 'none' && style.visibility !== 'hidden' && rect.width
                                && (rect.left < -0.5 || rect.right > innerWidth + 0.5);
                        }).length,
                    uncenteredContainers: [...document.querySelectorAll('.friendly-container, .auth-main, .auth-header, .shell')]
                        .filter(element => {
                            const rect = element.getBoundingClientRect();
                            return rect.width && Math.abs(rect.left - (innerWidth - rect.right)) > 1.5;
                        }).length
                })"""
            )
            assert measurement["scrollWidth"] <= measurement["clientWidth"], (
                f"{route} overflows at {width}px: {measurement}"
            )
            assert measurement["clippedNavLinks"] == 0, f"{route} clips navigation at {width}px"
            assert measurement["controlsOutsideViewport"] == 0, f"{route} has an inaccessible control at {width}px"
            assert measurement["uncenteredContainers"] == 0, f"{route} has an uncentered page container at {width}px"
            results.append({"route": route, "width": width, **measurement})
    return results
