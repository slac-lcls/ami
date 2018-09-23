SHELL:=/bin/bash
all:  test1 test2 test3

BASE=../AMI_client.py ../AMI_server.py ../AMI_common.py

test1: $(BASE) client1.py worker1a.py localCollector1.py globalCollector1.py
	rm -rf *.dat test1.log
	python3 client1.py >> test1.log
	python3 worker1a.py >> test1.log
	python3 localCollector1.py >> test1.log
	python3 globalCollector1.py >> test1.log
	make verify LOG=test1.log

test2: $(BASE) client1.py worker1a.py worker1b.py worker1c.py localCollector2a.py localCollector2b.py globalCollector2.py
	rm -rf *.dat test2.log
	python3 client1.py >> test2.log
	python3 worker1a.py >> test2.log
	python3 worker1b.py >> test2.log
	python3 worker1c.py >> test2.log
	python3 localCollector2a.py >> test2.log
	python3 localCollector2b.py >> test2.log
	python3 globalCollector2.py >> test2.log
	make verify LOG=test2.log

test3:	$(BASE) client3.py worker3a.py worker3b.py localCollector3.py globalCollector3.py
	rm -rf *.dat test3.log
	python3 client3.py >> test3.log
	python3 worker3a.py >> test3.log
	python3 worker3b.py >> test3.log
	python3 localCollector3.py >> test3.log
	python3 globalCollector3.py >> test3.log
	make verify LOG=test3.log

verify: $(LOG)
	@if [[ -e $(LOG).golden ]] ; then \
		rm -f .tmp1 .tmp2 ; \
		python3 symbologize.py < $(LOG) > .tmp1 ; \
		diff .tmp1 $(LOG).golden > .tmp2 ; \
		if [[ "`wc -l .tmp2`" == "0 .tmp2" ]]; then \
			echo Verification succeeded. ; \
		else \
			echo VERIFICATION FAILED, DIFFERENCES  ; \
			wc -l .tmp2 ; \
		fi ; \
	else \
		python3 symbologize.py < $(LOG) > $(LOG).golden ; \
		echo Saving golden log $(LOG).golden ; \
	fi
