import pygame, os, json, math, sys, random, array, asyncio

pygame.mixer.pre_init(44100, -16, 1, 512)
pygame.init()
WIDTH, HEIGHT= 1200, 800
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("roller baller")
clock = pygame.time.Clock()
FPS = 60

BASE = os.path.dirname(os.path.abspath(__file__))
SAVE_FILE = os.path.join(BASE, "highscore.json")
try: 
    with open(SAVE_FILE) as f:
        best_time = json.load(f).get("best")
except (OSError, ValueError):
    best_time = None
start_ticks = None
run_time = 0.0

def load(img):
    path = os.path.join(BASE, "assets", img)
    if not os.path.exists(path):
        sys.exit("missing asset" + path)
    return pygame.image.load(path).convert_alpha()

def remove_white_bg(surf, threshold=235):
    surf = surf.copy()
    w, h = surf.get_size()
    stack = ([(x, 0 ) for x in range(w)] + [(x, h - 1 ) for x in range (w)] + [(0, y) for y in range(h)] + [(w - 1, y) for y in range (h)])
    seen = set()
    while stack:
        x, y = stack.pop()
        if(x,y) in seen or not (0 <= x < w and 0 <= y < h):
            continue
        seen.add((x, y))
        color = surf.get_at((x, y))
        if color.a == 0:
            continue
        if min(color.r, color.g, color.b) < threshold:
            continue
        surf.set_at((x, y), (color.r, color.g, color.b, 0))
        stack += [(x + 1, y), (x - 1 ,y), (x, y + 1), (x, y - 1)]
    return surf

def draw_number(surface, n, x, y):
    for ch in str(n):
        img = digits_imgs[int(ch)]
        surface.blit(img, (x, y))
        x += img.get_width() + 2

def draw_time(surface, t, x, y):
    for ch in f"{t:.2f}":
        img = img_dot if ch == "." else digits_imgs[int(ch)]
        surface.blit(img, (x, y))
        x += img.get_width() + 2

img_ball = remove_white_bg(load("ball.png"))
BALL_SIZE = 40
img_ball = pygame.transform.smoothscale(img_ball, (BALL_SIZE, BALL_SIZE))
img_coin = load("coin.png")
img_bg = load("bg.png")
img_bg2 = load("bg2.png")
img_level2 = load("level2.png")
img_knob = load("knob.png")
mask2 = pygame.mask.from_surface(img_level2)
img_death = pygame.transform.smoothscale(load("death.png"), (WIDTH, HEIGHT))
img_win = load("win.png")
img_menu = load("menu.png")
img_settings = load("settings.png")
img_slider = load("slider.png")
img_dot = load("dot.png")
img_flag_off = load("flagoff.png")
img_flag_on = load("flagon.png")
img_star_on = load("star_on.png")
img_star_off = load("star_off.png")

THREE_STAR_TIME = 30.0
TWO_STAR_TIME = 50.0
stars = 0

CHECKPOINTS = [(3000, 500),(6500, 600)]
flags =  [img_flag_off.get_rect(center=p)for p in CHECKPOINTS]
flag_active = -1
checkpoint_pos = None

RATE = 44100
def load_sound(name):
    return pygame.mixer.Sound(os.path.join(BASE, "assets", name))

snd_jump = load_sound("jump.wav")
snd_coin = load_sound("coin.wav")
snd_death = load_sound("death.wav")
snd_win = load_sound("win.wav")
pygame.mixer.music.load(os.path.join(BASE, "assets", "music.wav"))
pygame.mixer.music.set_volume(0.4)
music_started = False


stage = 1
in_menu = True
in_settings = False
digits_imgs = [load(f"digit_{i}.png") for i in range(10)]
COIN_POSITIONS = [(800, 600), (1500, 400), (2245, 353), (4005, 421), (5790, 745)]
PLAY_CENTER = (561, 503)
PLAY_RADIUS = math.hypot(471 - 561, 500 - 503)
BACK_RECT = pygame.Rect(20, 20, 150, 60)
coins = [img_coin.get_rect(center=p) for p in COIN_POSITIONS]
score = 0
game_over = False
win = False
BG2_W = img_bg2.get_width()
world_w = WIDTH
REST_ANGLES = [45, 135, 225, 315]
SETTLE_SPEED = 2.0
SETTLE_EASE = 0.15
FLOOR_Y = HEIGHT - 60

SPEED_Y = 350
JUMP_Y = 500
speed_val = 0.5
jump_val = 0.5
dragging = None
BASE_ACCEL, BASE_MAX_SPEED, BASE_JUMP = 0.30, 20.0, -15.0

def apply_settings():
    global ACCEL, MAX_SPEED, JUMP_FORCE
    speed_mult = 0.5 * (4 ** speed_val)
    jump_mult = 0.7 + jump_val * 0.6
    ACCEL = BASE_ACCEL * speed_mult
    MAX_SPEED = BASE_MAX_SPEED * speed_mult
    JUMP_FORCE = BASE_JUMP * jump_mult

speed_track = img_slider.get_rect(center=(WIDTH // 2, SPEED_Y))
jump_track = img_slider.get_rect(center=(WIDTH // 2, JUMP_Y))
SLIDER_X1 = speed_track.left + img_knob.get_width() // 2
SLIDER_X2 = speed_track.right - img_knob.get_width() // 2
AIR_ACCEL = 0.18
FRICTION = 0.17
GRAVITY = 0.50
MAX_FALL = 16.0
JUMP_CUT = -4.0
SPIN_FACTOR = 3.0

class Player:
    def __init__(self, x, y, image):
        self.image = image
        self.size = image.get_width()
        self.rect = pygame.Rect(x, y, self.size, self.size)
        self.x = float(x)
        self.y = float(y)
        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = False
        self.angle = 0.0
        self.mask = pygame.mask.Mask((self.size, self.size), fill=True)

    def collides(self, dx=0, dy=0):
        if stage != 2:
            return False
        return mask2.overlap(self.mask, (self.rect.x + dx, self.rect.y + dy)) is not None
    
    def update(self, jump_pressed):
        was_grounded = self.on_ground
        keys = pygame.key.get_pressed()
        direction = int(keys[pygame.K_RIGHT]) - int(keys[pygame.K_LEFT])
        accel = ACCEL if self.on_ground else AIR_ACCEL
        if direction != 0:
            self.vx += direction * accel
        elif self.on_ground:
            if abs(self.vx) <= FRICTION:
                self.vx = 0
            else:
                self.vx -= FRICTION if self.vx > 0 else -FRICTION
        self.vx = max(-MAX_SPEED, min(MAX_SPEED, self.vx))

        if jump_pressed and self.on_ground :
            self.vy = JUMP_FORCE
            self.on_ground = False
            snd_jump.play()

        if not keys[pygame.K_SPACE] and self.vy < JUMP_CUT:
            self.vy = JUMP_CUT
        self.vy = min(self.vy + GRAVITY, MAX_FALL)

        self.x += self.vx
        self.rect.x = round(self.x)
        if self.collides():
            climbed = False
            up = 0
            if was_grounded:
                step = int(abs(self.vx) * 1.5) + 4
                for up in range(1, step + 1):
                    self.rect.y -= 1
                    if not self.collides():
                        climbed = True
                        break
                if climbed:
                    self.y = float(self.rect.y)
                else:
                    self.rect.y += up
            if not climbed:
                n = 0
                while self.collides() and n < 100:
                    self.rect.x += -1 if self.vx > 0 else 1
                    n += 1
                self.x = float(self.rect.x)
                self.vx = 0

        self.y += self.vy
        self.rect.y = round(self.y)
        n = 0
        while self.collides() and n < 100:
            self.rect.y += -1 if self.vy > 0 else 1
            n += 1
        if n:
            self.y = float(self.rect.y)
            self.vy = 0

        if was_grounded and self.vy >= 0 and not self.collides(0, 1):
            for d in range(2, int(abs(self.vx)) + 8):
                if self.collides(0, d):
                    self.rect.y += d - 1
                    self.y = float(self.rect.y)
                    self.vy = 0
                    break

        if stage == 1:
            if self.rect.bottom >= FLOOR_Y:
                self.rect.bottom = FLOOR_Y
                self.y = float(self.rect.y)
                self.vy = 0 
                self.on_ground = True
            else:
                self.on_ground = False
        else:
            self.on_ground = self.vy >= 0 and self.collides(0, 1)

        if stage == 1 and self.rect.left < 0:
            self.rect.left = 0
            self.x = float(self.rect.x)
            self.vx = 0

        if stage == 2 and self.rect.right > world_w:
            self.rect.right = world_w
            self.x = float(self.rect.x)
            self.vx = 0

        self.angle = (self.angle - self.vx * SPIN_FACTOR) % 360
        if self.on_ground and direction == 0 and abs(self.vx) < SETTLE_SPEED:
            target = min(REST_ANGLES, key=lambda a: abs((a - self.angle + 180) % 360 - 180))
            diff = (target - self.angle + 180) % 360 - 180 
            self.angle = (self.angle + diff * SETTLE_EASE) % 360

    def draw(self, surface, cam_x=0):
        rotated = pygame.transform.rotate(self.image, self.angle)
        center = (self.rect.centerx - cam_x, self.rect.centery)
        surface.blit(rotated, rotated.get_rect(center=center))



apply_settings()
player = Player(100, 100, img_ball)
cam_x = 0.0

async def main():
    global stage, in_menu, in_settings, dragging, speed_val, jump_val, coins, score, game_over, win, world_w, cam_x, start_ticks, run_time, best_time, flag_active, checkpoint_pos, stars, music_started

    while True:
        jump_pressed = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if in_settings:
                        in_settings = False
                    else:
                        pygame.quit()
                        sys.exit()
                if in_menu and not in_settings and event.key == pygame.K_RETURN:
                    in_menu = False
                if event.key == pygame.K_SPACE and not in_menu: 
                    jump_pressed = True
                if (game_over or win) and event.key == pygame.K_r:
                    if win or checkpoint_pos is None:
                        coins = [img_coin.get_rect(center=p) for p in COIN_POSITIONS]
                        score = 0
                        flag_active = -1
                        checkpoint_pos = None
                        start_ticks = None
                        run_time = 0.0
                        spawn = (50, 100)
                    else:
                        spawn = checkpoint_pos
                    game_over = False
                    win = False
                    stage = 2
                    world_w = BG2_W
                    player.x, player.y = float(spawn[0]), float(spawn[1])
                    player.rect.topleft = (spawn[0], spawn[1])
                    player.vx = player.vy = 0.0
                    player.angle = 0.0
                    cam_x = max(0, min(spawn[0] - WIDTH / 2, BG2_W - WIDTH))

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if in_menu and not in_settings:
                    if event.pos[1] < 120:
                        in_settings = True
                    elif math.hypot(event.pos[0] - PLAY_CENTER[0], event.pos[1] - PLAY_CENTER[1]) <= PLAY_RADIUS:
                        in_menu = False
                        pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_ARROW)
                elif in_settings:
                    if BACK_RECT.collidepoint(event.pos):
                        in_settings = False
                    elif speed_track.union(jump_track).inflate(50, 60).collidepoint(event.pos):
                        if abs(event.pos[1] - SPEED_Y) < abs(event.pos[1] - JUMP_Y):
                            dragging = "speed"
                        else:
                            dragging = "jump"
                elif stage == 2:
                    print((event.pos[0] + round(cam_x), event.pos[1]))

        if in_menu:
            mx, my = pygame.mouse.get_pos()

            if in_settings:
                if dragging and pygame.mouse.get_pressed()[0]:
                    v = max(0.0, min(1.0, (mx - SLIDER_X1) / (SLIDER_X2 - SLIDER_X1)))
                    if dragging == "speed":
                        speed_val = v
                    else:
                        jump_val = v
                    apply_settings()
                else:
                    dragging = None
                screen.fill((0, 0, 0))
                screen.blit(img_settings, (0, 0))
                screen.blit(img_slider, speed_track)
                screen.blit(img_slider, jump_track)
                for val, y in ((speed_val, SPEED_Y), (jump_val, JUMP_Y)):
                    kx = SLIDER_X1 + val * (SLIDER_X2 - SLIDER_X1)
                    screen.blit(img_knob, img_knob.get_rect(center=(kx, y)))
            else:
                over = (not in_settings) and (my < 120 or math.hypot(mx - PLAY_CENTER[0], my - PLAY_CENTER[1]) <= PLAY_RADIUS)
                pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND if over else pygame.SYSTEM_CURSOR_ARROW)
                screen.blit(img_menu, (0, 0))

            pygame.display.flip()
            clock.tick(FPS)
            await asyncio.sleep(0)
            continue

        if not music_started:
            pygame.mixer.music.play(-1)
            music_started = True

        if start_ticks is None:
            start_ticks = pygame.time.get_ticks()

        if not game_over and not win:
            run_time = (pygame.time.get_ticks() - start_ticks) / 1000
            player.update(jump_pressed)
            if player.rect.top > HEIGHT:
                game_over = True
                snd_death.play()

            if stage == 2 and player.rect.x >= 9000 and len(coins) == 0:
                win = True
                stars = 3 if run_time <= THREE_STAR_TIME else 2 if run_time <= TWO_STAR_TIME else 1
                if best_time is None or run_time < best_time:
                    best_time = run_time
                    with open(SAVE_FILE, "w") as f:
                        json.dump({"best": best_time}, f)

                snd_win.play()
                
            if stage == 2 and len(coins) > 0 and player.rect.right > 8400:
                player.rect.right = 8400
                player.x = float(player.rect.x)
                player.vx = 0

        if stage == 2:
            for c in coins[:]:
                if player.rect.colliderect(c):
                    coins.remove(c)
                    score += 1
                    snd_coin.play()

            for i, f in enumerate(flags):
                if i > flag_active and player.rect.colliderect(f):
                    flag_active = i
                    checkpoint_pos = (f.centerx - player.size // 2, f.bottom - player.size - 10)
                
        if stage == 1 and player.rect.centerx > WIDTH:
            stage = 2
            world_w = BG2_W
            player.x = 0.0
            player.rect.x = 0
            cam_x = 0.0

        if stage == 1:
            screen.blit(img_bg, (0, 0))

        else:
            target_x = player.rect.centerx - WIDTH / 2 + player.vx * 12
            cam_x += (target_x - cam_x) * 0.1
            cam_x = max(0, min(cam_x, BG2_W - WIDTH))
            screen.blit(img_bg2, (-round(cam_x), 0))

        if stage == 2 and player.rect.centerx < 0:
            stage = 1
            world_w = WIDTH
            player.x = float(WIDTH - player.size)
            player.rect.x = WIDTH - player.size
            cam_x = 0.0

        if stage == 2:
            screen.blit(img_level2, (-round(cam_x), 0))
            for c in coins:
                screen.blit(img_coin, (c.x - round(cam_x), c.y))
            for i, f in enumerate(flags):
                img = img_flag_on if  i <= flag_active else img_flag_off
                screen.blit(img, (f.x - round(cam_x), f.y))
                


        
        player.draw(screen, round(cam_x))
        screen.blit(img_coin, (20, 20))
        draw_number(screen, score, 20 + img_coin.get_width() + 10, 20)
        if game_over:
            screen.blit(img_death,(0, 0))
        if win:
            screen.blit(img_win, (0, 0))
            w = img_star_on.get_width()
            for i in range(3):
                img = img_star_on if i < stars else img_star_off
                screen.blit(img, (WIDTH // 2 - 3 * w //2 + i * w, 300))
        draw_time(screen, run_time, WIDTH - 260, 20)
        pygame.display.flip()
        clock.tick(FPS)
        await asyncio.sleep(0)

asyncio.run(main())
