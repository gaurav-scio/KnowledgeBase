""" Simple Python script to query SIDER for drug adverse events"
    No extra libraries required.

# Authors: Richard D Boyce and Vojtech Huser
#
# May 2014
# 

"""

import json
import urllib2
import urllib
import traceback
import sys 
import pickle
import codecs

sys.path = sys.path + ['.']

#############  GLOBALS ###################################################################

SIDER_SPARQL = "http://s2.semanticscience.org:12050/sparql"

LOG_FILE = "sider_gov_queryresults.log"
OUT_FILE = "sider__gov_queryresults.tsv"
PICKLE_FILE = "sider_gov_queryresults.pickle" # where a python data structure containing the results will be stored


drugs = "drugsToSearch.txt"
HOIs = "HOIsToSearch.txt"

## ADJUST THE OFFSETS AND LIMITS IF THE RESULT SETS ARE VERY LARGE
offset = 0
maxoffset = 20000
limit = 5000

############## QUERY  ##################################################################
def getQueryString(hoi, offset, limit):
    return """ 
SELECT ?dLabel date_SPL_setid
WHERE {
 ?d a <http://bio2rdf.org/sider_vocabulary:Drug>;
    <http://bio2rdf.org/sider_vocabulary:generic-name> ?dNameURI;
    <http://bio2rdf.org/sider_vocabulary:side-effect> %s;
    <http://bio2rdf.org/bio2rdf_vocabulary:identifier> ?date_SPL_setid.

 ?dNameURI <http://www.w3.org/2000/01/rdf-schema#label> ?dLabel.
}
OFFSET %d
LIMIT %d

""" % (hoi, offset, limit)

def getTrialDict():
    """A dictionary to hold selected data from SIDER"""
    d = {
        "trialLabel":None,
        "trialURI":None,
        "interventionLabel":None,
        "interventionURI":None,
        "conditionLabel":None,
        "conditionURI":None,
        "completionDate":None,        
        "dataSource":None
      }

    return d

def createTrialDrugIntervention(qResult, drug, sparql_service):
    newTrial = getTrialDict()
    newTrial["dataSource"] = sparql_service
    newTrial["trialLabel"] = qResult["trialLabel"]["value"]
    newTrial["trialURI"] = qResult["trialURI"]["value"]
    newTrial["interventionLabel"] = drug
    newTrial["interventionURI"] = qResult["interventionURI"]["value"]
    newTrial["conditionLabel"] = qResult["conditionLabel"]["value"]
    newTrial["conditionURI"] = qResult["conditionURI"]["value"]
    newTrial["completionDate"] = qResult["completionDate"]["value"]
       
    return newTrial


############## SPARQL FUNCTIONS  ##################################################################
def query(q,epr,f='application/json'):
    """Function that uses urllib/urllib2 to issue a SPARQL query.
       By default it requests json as data format for the SPARQL resultset"""

    try:
        params = {'query': q}
        params = urllib.urlencode(params)
        opener = urllib2.build_opener(urllib2.HTTPHandler)
        request = urllib2.Request(epr+'?'+params)
        request.add_header('Accept', f)
        request.get_method = lambda: 'GET'
        url = opener.open(request)
        return url.read()
    except Exception, e:
        traceback.print_exc(file=sys.stdout)
        raise e


def queryEndpoint(sparql_service, q):
    print "query string: %s" % q
    json_string = query(q, sparql_service)
    #print "%s" % json_string
    resultset=json.loads(json_string)
    
    return resultset

########### MAIN  #####################################################################

if __name__ == "__main__":

    logf = codecs.open(LOG_FILE,'w','utf-8')
    outf = codecs.open(OUT_FILE,'w','utf-8')

    drugList = ["Omalizumab"]
    
    ## ALTERNATIVELY, WRITE DRUGS TO FILE
    # f = open(drugF, "r")
    # buf = f.read()
    # f.close()
    # drugList = buf.strip().split(";")

    ctD = {}
    sparql_service = CT_SPARQL

   
    for drugSymbol in drugList:
        logf.write("INFO: trying symbol %s\n" % drugSymbol)
        q = getQueryString(drugSymbol, offset, limit) 
        resultset = queryEndpoint(sparql_service, q)

        if len(resultset["results"]["bindings"]) == 0:
            logf.write("INFO: no results for drug %s" % drugSymbol)
            continue
        
        goFlag = True
        while len(resultset["results"]["bindings"]) != 0 and goFlag:

            # print json.dumps(resultset,indent=1) # you can dump the results as JSON if needed
            for i in range(0, len(resultset["results"]["bindings"])):
                qResult = resultset["results"]["bindings"][i]
                newCT = createTrialDrugIntervention(qResult, drugSymbol, sparql_service)
            
                if not ctD.has_key(drugSymbol):
                    ctD[drugSymbol] = [newCT]
                else:
                    ctD[drugSymbol].append(newCT)
                    
            if len(resultset["results"]["bindings"]) == offset:
                offset += offset
                q = getQueryString(drugSymbol, offset, limit)
                resultset = queryEndpoint(sparql_service, q)
            else:
                goFlag = False

    # serialize the results 
    pickleF = PICKLE_FILE
    f = open(pickleF,"w")
    pickle.dump(ctD, f)
    f.close()

    # write a summary to log
    for k,v in ctD.iteritems():
        logf.write("%d trials found for drug %s" % (len(v),k))

    logf.write("mapping data saved to %s" % pickleF)
        
    # write tab delimitted output
    outf.write("%s\n" % "\t".join(["drug"] + getTrialDict().keys()))
    for k,v in ctD.iteritems():
        for elt in v:
            outf.write("%s" % k)
            for key in getTrialDict().keys():
                outf.write("\t%s" % elt[key])
            outf.write("\n")

    logf.close()
    outf.close()

        

