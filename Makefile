PY ?= python3

.PHONY: arch verify clean

arch: ## 分析 -> 生成图 URL -> 同步 README.md 与 README.zh.md
	$(PY) scripts/analyze_arch.py --root . --out arch.json
	$(PY) scripts/build_diagram.py arch.json --out diagram.md
	$(PY) scripts/update_readme.py --image-file diagram.md \
		--readme README.md --readme README.zh.md

verify: arch ## 重新生成并 HTTP 校验两份 README 中所有内嵌的图表 URL
	@grep -ho 'https://x-cmd.com/draw/arch2?[^)]*' README.md README.zh.md \
		| sort -u | while read -r url; do \
		code=$$(curl -s -o /dev/null -w '%{http_code}' "$$url"); \
		echo "HTTP $$code  $${url:0:90}..."; \
	done

clean:
	rm -f arch.json diagram.md
