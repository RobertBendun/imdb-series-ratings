
all: title.basics.tsv title.episode.tsv title.ratings.tsv

%.gz:
	wget https://datasets.imdbws.com/$@ -O $@

%.tsv: %.tsv.gz
	gunzip $<
