PY ?= python3

.PHONY: arch verify clean

arch: ## 分析 repo -> 生成 x-cmd draw URL -> 记录 URL 到 README
	$(PY) scripts/analyze_arch.py --root . --out arch.json
	$(PY) scripts/build_diagram.py arch.json --out diagram.url
	$(PY) scripts/update_readme.py --url-file diagram.url \
		--readme README.md --readme README.zh.md

verify: arch ## 重新生成并 HTTP 校验两份 README 中所有内嵌的图表 URL
	@grep -ho 'https://x-cmd.com/draw/arch2?[^)]*' README.md README.zh.md \
		| sort -u | while read -r url; do \
		code=$$(curl -sL -o /dev/null -w '%{http_code}' "$$url"); \
		echo "HTTP $$code  $${url:0:90}..."; \
	done

clean:
	rm -f arch.json diagram.url
