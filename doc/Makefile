sources := $(wildcard *.md)
html := $(patsubst %.md,%.html,$(sources))

all:	$(html)

%.html:	%.md
	markdown $< > $@

clean:
	rm -f $(html)
