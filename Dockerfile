FROM ubuntu:14.04.3
RUN apt-get update

RUN apt-get -y install python python-pip libxml2-dev libxslt1-dev libz-dev gfortran liblapack-dev libblas-dev libxml2 python-dev libjpeg8-dev wget

#Add the application files
ADD . .

#Download trained classifier data
RUN wget https://s3-us-west-2.amazonaws.com/grits-classifiers/current_classifier.tar.gz
RUN tar -zxf current_classifier.tar.gz
RUN cp -r current_classifier simple_api/

#Install pip dependencies for simple API
RUN pip install -r simple-api/requirements.txt 

EXPOSE 5000
ENV PYTHONPATH="/annie"
CMD bash run.sh
