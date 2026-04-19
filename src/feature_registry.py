"""
Canonical registry of feature names and their module paths.

Shared between src/main.py and src/config_validator.py to avoid
duplication and circular imports.
"""

# Map of feature names to their module paths
FEATURE_MODULES = {
    "tic_tac_toe": "src.display.tic_tac_toe",
    "snake": "src.display.snake",
    "pong": "src.display.pong",
    "breakout": "src.display.breakout",
    "billiards": "src.display.billiards",
    "time_display": "src.display.time_display",
    "bitcoin_price": "src.display.bitcoin_price",
    "youtube_stream": "src.display.youtube_stream",
    "fire": "src.display.fire",
    "plasma": "src.display.plasma",
    "matrix_rain": "src.display.matrix_rain",
    "starfield": "src.display.starfield",
    "game_of_life": "src.display.game_of_life",
    "rainbow_waves": "src.display.rainbow_waves",
    "weather": "src.display.weather",
    "text_scroller": "src.display.text_scroller",
    "stock_ticker": "src.display.stock_ticker",
    "sp500_heatmap": "src.display.sp500_heatmap",
    "binary_clock": "src.display.binary_clock",
    "countdown": "src.display.countdown",
    "lava_lamp": "src.display.lava_lamp",
    "living_world": "src.display.living_world",
    "qr_code": "src.display.qr_code",
    "slideshow": "src.display.slideshow",
    "galaga": "src.display.galaga",
    "space_invaders": "src.display.space_invaders",
    "logo_wholefoods": "src.display.logo_wholefoods",
    "github_stats": "src.display.github_stats",
    "tanks": "src.display.tanks",
    "wireframe": "src.display.wireframe",
    "maze_3d": "src.display.maze_3d",
    "terrain_ball": "src.display.terrain_ball",
    "system_stats": "src.display.system_stats",
    "base6_clock": "src.display.base6_clock",
    "tetris": "src.display.tetris",
}
