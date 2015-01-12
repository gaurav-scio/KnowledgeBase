# pmSearch2rdf.py
#
# Convert the result of a pubmed drug-HOI evidence search to Open Data Annotation
#
# Author: Richard D Boyce, PhD
# 2014/2015
#

import sys
sys.path = sys.path + ['.']

import re, codecs, uuid, datetime
import json
from rdflib import Graph, Literal, Namespace, URIRef, RDF, RDFS
from lxml import etree
from lxml.etree import XMLParser, parse

## The result of the query in queryDrugHOIAssociations.psql
SEARCH_RESULTS = "drug-hoi-associations-from-mesh.tsv"

# TERMINOLOGY MAPPING FILES 
## NOTE: the drug concepts are mapped directly to RxNorm here but the
##       HOIs are retained as MeSH and then mapped using the Standard
##       Vocabu lary at load time by the code in
##       Schema/postgres/mergeCountsFromIntegratedSources.py based on
##       config information present in
##       Schema/postgres/integratedSources.conf
RXNORM_TO_MESH = "../terminology-mappings/RxNorm-to-MeSH/mesh-to-rxnorm-standard-vocab-v5.txt"
MESH_TO_STANDARD_VOCAB = "../terminology-mappings/StandardVocabToMeSH/mesh-to-standard-vocab-v5.txt"
MESH_PHARMACOLOGIC_ACTION_MAPPINGS = "../terminology-mappings/MeSHPharmocologicActionToSubstances/pa2015.xml"

# OUTPUT DATA FILE
OUTPUT_FILE = "drug-hoi-pubmed-mesh.rdf"

############################################################
#  Load the  MeSH Pharmacologic Action mappings from an XML file
############################################################
pharmActionMaptD = {}
p = XMLParser(huge_tree=True)
tree = parse(MESH_PHARMACOLOGIC_ACTION_MAPPINGS, parser=p)
l = tree.xpath('PharmacologicalAction')
for elt in l:
    descriptorUI = elt.xpath('DescriptorReferredTo/DescriptorUI')[0].text
    descriptorName = elt.xpath('DescriptorReferredTo/DescriptorName/String')[0].text
    pharmacologicalActionSubstanceL = elt.xpath('PharmacologicalActionSubstanceList/Substance')
    substancesL = []
    for substanceElt in pharmacologicalActionSubstanceL:
        recordUI = substanceElt.xpath('RecordUI')[0].text
        recordName = substanceElt.xpath('RecordName/String')[0].text
        substancesL.append({'recordUI':recordUI,'recordName':recordName})

    pharmActionMaptD[descriptorUI] = {'descriptorName':descriptorName, 'substancesL':substancesL}

############################################################
#  Load the Drug ad HOI mappings that include OHDSI Standard Vocab codes
############################################################
DRUGS_D = {}
f = open(RXNORM_TO_MESH,"r")
buf = f.read()
f.close()
l = buf.split("\n")
for elt in l[1:]:
    if elt.strip() == "":
        break

    (mesh,pt,rxcui,concept_name,ohdsiID,conceptClassId) = [x.strip() for x in elt.split("|")]
    if DRUGS_D.get(mesh): # add a synonymn
        DRUGS_D[mesh][1].append(pt)
    else: # create a new record
        DRUGS_D[mesh] = (rxcui, [pt], ohdsiID)

MESH_D_SV = {}
f = open(MESH_TO_STANDARD_VOCAB, "r")
buf = f.read()
f.close()
l = buf.split("\n")
for elt in l[1:]: # skip header
    if elt.strip() == "":
        break

    (imeds,label,mesh) = [x.strip() for x in elt.split("|")]
    MESH_D_SV[mesh] = imeds

############################################################
## set up an RDF Open Annotation Data  graph
############################################################
# identify namespaces for other ontologies to be used                                                                                    
dcterms = Namespace("http://purl.org/dc/terms/")
pav = Namespace("http://purl.org/pav")
dctypes = Namespace("http://purl.org/dc/dcmitype/")
sio = Namespace('http://semanticscience.org/resource/')
oa = Namespace('http://www.w3.org/ns/oa#')
aoOld = Namespace('http://purl.org/ao/core/') # needed for AnnotationSet and item until the equivalent is in Open Data Annotation
cnt = Namespace('http://www.w3.org/2011/content#')
siocns = Namespace('http://rdfs.org/sioc/ns#')
swande = Namespace('http://purl.org/swan/1.2/discourse-elements#')
ncbit = Namespace('http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl#')
mesh = Namespace('http://purl.bioontology.org/ontology/MESH/')
meddra = Namespace('http://purl.bioontology.org/ontology/MEDDRA/')
rxnorm = Namespace('http://purl.bioontology.org/ontology/RXNORM/')
pubmed = Namespace('http://www.ncbi.nlm.nih.gov/pubmed/')
ohdsi = Namespace('http://purl.org/net/ohdsi#')
poc = Namespace('http://purl.org/net/nlprepository/ohdsi-pubmed-mesh-poc#')

graph = Graph()
graph.namespace_manager.reset()
graph.namespace_manager.bind("dcterms", "http://purl.org/dc/terms/")
graph.namespace_manager.bind("pav", "http://purl.org/pav");
graph.namespace_manager.bind("dctypes", "http://purl.org/dc/dcmitype/")
graph.namespace_manager.bind('sio', 'http://semanticscience.org/resource/')
graph.namespace_manager.bind('oa', 'http://www.w3.org/ns/oa#')
graph.namespace_manager.bind('aoOld', 'http://purl.org/ao/core/') # needed for AnnotationSet and item until the equivalent is in Open Data Annotation
graph.namespace_manager.bind('cnt', 'http://www.w3.org/2011/content#')
graph.namespace_manager.bind('siocns','http://rdfs.org/sioc/ns#')
graph.namespace_manager.bind('swande','http://purl.org/swan/1.2/discourse-elements#')
graph.namespace_manager.bind('ncbit','http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl#')
graph.namespace_manager.bind('mesh', 'http://purl.bioontology.org/ontology/MESH/')
graph.namespace_manager.bind('meddra','http://purl.bioontology.org/ontology/MEDDRA/')
graph.namespace_manager.bind('rxnorm','http://purl.bioontology.org/ontology/RXNORM/')
graph.namespace_manager.bind('pubmed', 'http://www.ncbi.nlm.nih.gov/pubmed/')
graph.namespace_manager.bind('ohdsi', 'http://purl.org/net/ohdsi#')
graph.namespace_manager.bind('poc','http://purl.org/net/nlprepository/ohdsi-pubmed-mesh-poc#')

### open annotation ontology properties and classes
graph.add((dctypes["Collection"], RDFS.label, Literal("Collection"))) # Used in lieau of the AnnotationSet https://code.google.com/p/annotation-ontology/wiki/AnnotationSet
graph.add((dctypes["Collection"], dcterms["description"], Literal("A collection is described as a group; its parts may also be separately described. See http://dublincore.org/documents/dcmi-type-vocabulary/#H7")))

graph.add((oa["Annotation"], RDFS.label, Literal("Annotation")))
graph.add((oa["Annotation"], dcterms["description"], Literal("Typically an Annotation has a single Body (oa:hasBody), which is the comment or other descriptive resource, and a single Target (oa:hasTarget) that the Body is somehow 'about'. The Body provides the information which is annotating the Target. See  http://www.w3.org/ns/oa#Annotation")))

graph.add((oa["annotatedBy"], RDFS.label, Literal("annotatedBy")))
graph.add((oa["annotatedBy"], RDF.type, oa["objectproperties"]))

graph.add((oa["annotatedAt"], RDFS.label, Literal("annotatedAt")))
graph.add((oa["annotatedAt"], RDF.type, oa["dataproperties"]))

graph.add((oa["TextQuoteSelector"], RDFS.label, Literal("TextQuoteSelector")))
graph.add((oa["TextQuoteSelector"], dcterms["description"], Literal("A Selector that describes a textual segment by means of quoting it, plus passages before or after it. See http://www.w3.org/ns/oa#TextQuoteSelector")))

graph.add((oa["hasSelector"], RDFS.label, Literal("hasSelector")))
graph.add((oa["hasSelector"], dcterms["description"], Literal("The relationship between a oa:SpecificResource and a oa:Selector. See http://www.w3.org/ns/oa#hasSelector")))

graph.add((oa["SpecificResource"], RDFS.label, Literal("SpecificResource")))
graph.add((oa["SpecificResource"], dcterms["description"], Literal("A resource identifies part of another Source resource, a particular representation of a resource, a resource with styling hints for renders, or any combination of these. See http://www.w3.org/ns/oa#SpecificResource")))

# these predicates are specific to SPL annotation
graph.add((sio["SIO_000628"], RDFS.label, Literal("refers to")))
graph.add((sio["SIO_000628"], dcterms["description"], Literal("refers to is a relation between one entity and the entity that it makes reference to.")))

graph.add((sio["SIO_000563"], RDFS.label, Literal("describes")))
graph.add((sio["SIO_000563"], dcterms["description"], Literal("describes is a relation between one entity and another entity that it provides a description (detailed account of)")))

graph.add((sio["SIO_000338"], RDFS.label, Literal("specifies")))
graph.add((sio["SIO_000338"], dcterms["description"], Literal("A relation between an information content entity and a product that it (directly/indirectly) specifies")))

graph.add((poc['MeshDrug'], RDFS.label, Literal("MeSH Drug code")))
graph.add((poc['MeshDrug'], dcterms["description"], Literal("Drug code in the MeSH vocabulary.")))

graph.add((poc['RxnormDrug'], RDFS.label, Literal("Rxnorm Drug code")))
graph.add((poc['RxnormDrug'], dcterms["description"], Literal("Drug code in the Rxnorm vocabulary.")))

graph.add((poc['MeshHoi'], RDFS.label, Literal("MeSH HOI code")))
graph.add((poc['MeshHoi'], dcterms["description"], Literal("HOI code in the MeSH vocabulary.")))

graph.add((poc['MeddraHoi'], RDFS.label, Literal("Meddra HOI code")))
graph.add((poc['MeddraHoi'], dcterms["description"], Literal("HOI code in the Meddra vocabulary.")))

################################################################################

# Load the results of applying the Avillach et al method for
# identifying drug-ADR associations in MEDLINE using MeSH headings
# TODO: consider using an iterator for this
(PMID, ADR_DRUG_LABEL, ADR_DRUG_UI, ADR_HOI_LABEL, ADR_HOI_UI, PUB_TYPE, PUB_TYPE_UI) = range(0,7)
f = open(SEARCH_RESULTS,'r')
buf = f.read()
f.close()
recL = [x.strip().split("\t") for x in buf.split("\n")]

# Start building the open annotation data graph
annotationSetCntr = 1
annotationItemCntr = 1
annotationBodyCntr = 1
annotationEvidenceCntr = 1

annotatedCache = {} # indexes annotation ids by pmid
adeAgentCollectionCache = {} # indexes the collection of agents associated with and ADE
adeEffectCollectionCache = {} # indexes the collection of effects associated with and ADE
currentAnnotation = annotationItemCntr

currentAnnotSet = 'ohdsi-pubmed-mesh-annotation-set-%s' % annotationSetCntr 
annotationSetCntr += 1
graph.add((poc[currentAnnotSet], RDF.type, oa["DataAnnotation"])) # TODO: find out what is being used for collections in OA
graph.add((poc[currentAnnotSet], oa["annotatedAt"], Literal(datetime.date.today())))
graph.add((poc[currentAnnotSet], oa["annotatedBy"], URIRef(u"http://www.pitt.edu/~rdb20/triads-lab.xml#TRIADS")))

for elt in recL:  
    ###################################################################
    ### Each annotations holds one target that points to the source
    ### record in pubmed, and one or more bodies each of which
    ### indicates the MeSH terms that triggered the result and holds
    ### some metadata
    ###################################################################
    currentAnnotItem = None
    createNewTarget = False
    if annotatedCache.has_key(elt[PMID]):
        currentAnnotation = annotatedCache[elt[PMID]]
    else:
        currentAnnotation = annotationItemCntr
        annotatedCache[elt[PMID]] = currentAnnotation
        annotationItemCntr += 1
        createNewTarget = True
    
    currentAnnotItem = "ohdsi-pubmed-mesh-annotation-item-%s" % currentAnnotation

    if createNewTarget:
        graph.add((poc[currentAnnotSet], aoOld["item"], poc[currentAnnotItem])) # TODO: find out what is being used for items of collections in OA
        graph.add((poc[currentAnnotItem], RDF.type, oa["DataAnnotation"])) 
        graph.add((poc[currentAnnotItem], RDF.type, ohdsi["PubMedDrugHOIAnnotation"])) # TODO: should be a subclass of oa:DataAnnotation
        graph.add((poc[currentAnnotItem], oa["annotatedAt"], Literal(datetime.date.today())))
        graph.add((poc[currentAnnotItem], oa["annotatedBy"], URIRef(u"http://www.pitt.edu/~rdb20/triads-lab.xml#TRIADS")))
        graph.add((poc[currentAnnotItem], oa["motivatedBy"], oa["tagging"]))
        
        currentAnnotTargetUuid = URIRef(u"urn:uuid:%s" % uuid.uuid4())
        graph.add((poc[currentAnnotItem], oa["hasTarget"], currentAnnotTargetUuid))
        graph.add((currentAnnotTargetUuid, RDF.type, oa["SpecificResource"]))
        graph.add((currentAnnotTargetUuid, oa["hasSource"], pubmed[elt[PMID]]))

        # TODO: use the MeSH UIs to generate purls for the pub types
        # TODO: add more publication types
        if elt[PUB_TYPE] == "Clinical Trial": 
            graph.add((currentAnnotTargetUuid, ohdsi["MeshStudyType"], Literal("clinical trial (publication type)")))
        elif elt[PUB_TYPE] == "Case Reports": 
            graph.add((currentAnnotTargetUuid, ohdsi["MeshStudyType"], Literal("case reports (publication type)")))
        elif elt[PUB_TYPE] == "Meta-Analysis": 
            graph.add((currentAnnotTargetUuid, ohdsi["MeshStudyType"], Literal("other (publication type)")))

    # Specify the bodies of the annotation - for this type each
    # body contains the MESH drug and condition as a semantic tag
    currentAnnotationBody = "ohdsi-pubmed-mesh-annotation-annotation-body-%s" % annotationBodyCntr
    annotationBodyCntr += 1
         
    graph.add((poc[currentAnnotItem], oa["hasBody"], poc[currentAnnotationBody]))
    graph.add((poc[currentAnnotationBody], RDFS.label, Literal("Drug-HOI tag for %s" % k)))
    graph.add((poc[currentAnnotationBody], RDF.type, ohdsi["OHDSIMeshTags"])) # TODO: this is not yet formalized in a public ontology but should be
    graph.add((poc[currentAnnotationBody], dcterms["description"], Literal("Drug-HOI body from MEDLINE PMID %s using MESH drug %s (%s) and HOI %s (%s)" % (elt[PMID], elt[ADR_DRUG_LABEL], elt[ADR_DRUG_UI], elt[ADR_HOI_LABEL], elt[ADR_HOI_UI)))))

    ### INCLUDE THE MESH TAGS FROM THE RECORD AS PREFERRED TERMS AS
    ### WELL AS DATA FROM THE DRUG AND HOI QUERY
    graph.add((poc[currentAnnotationBody], ohdsi['MeshDrug'], mesh[elt[ADR_DRUG_UI]])) 
    if DRUGS_D.has_key(elt[ADR_DRUG_UI]):
        graph.add((poc[currentAnnotationBody], ohdsi['RxnormDrug'], rxnorm[DRUGS_D[elt[ADR_DRUG_UI]][0]]))
        graph.add((poc[currentAnnotationBody], ohdsi['ImedsDrug'], ohdsi[DRUGS_D[elt[ADR_DRUG_UI]][2]]))
    else:
        print "ERROR: no RxNorm equivalent to the MeSH drug %s, skipping" % (elt[ADR_DRUG_UI])
        continue

    if MESH_D_SV.has_key(elt[ADR_HOI_UI]):
        graph.add((poc[currentAnnotationBody], ohdsi['ImedsHoi'], ohdsi[MESH_D_SV[elt[ADR_HOI_UI]]]))
        graph.add((poc[currentAnnotationBody], ohdsi['MeshHoi'], mesh[elt[ADR_HOI_UI]]))
    else:
        print "ERROR: no OHDSI/IMEDS equivalent to the MeSH drug %s, skipping" % (elt[ADR_DRUG_UI])
        continue

    # add the ADE agent to a collection in the body
    # if not adeAgentCollectionCache.has_key(elt[PMID]):
    #     collectionHead = URIRef(u"urn:uuid:%s" % uuid.uuid4())
    #     graph.add((poc[currentAnnotationBody], ohdsi['adeAgents'], collectionHead))
    #     graph.add((collectionHead, ohdsi['adeAgent'], Literal(elt[ADR_DRUG_UI])))
    #     adeAgentCollectionCache[elt[PMID]] = [(elt[ADR_DRUG_UI],collectionHead)]
    # else:
    #     agentTplL = adeAgentCollectionCache[elt[PMID]]
    #     prevAgentsL = [x[0] for x in agentTplL]
    #     if elt[ADR_DRUG_UI] not in prevAgentsL:
    #         collectionHead = agentTplL[0][1] # pull the UUID already create for this collection head to add a new agent
    #         graph.add((collectionHead, ohdsi['adeAgent'], Literal(elt[ADR_DRUG_UI])))
    #         adeAgentCollectionCache[elt[PMID]].append((elt[ADR_DRUG_UI],collectionHead))
    

    # # add the ADE effect to a collection in the body
    # if not adeEffectCollectionCache.has_key(elt[PMID]):
    #     collectionHead = URIRef(u"urn:uuid:%s" % uuid.uuid4())
    #     graph.add((poc[currentAnnotationBody], ohdsi['adeEffects'], collectionHead))
    #     graph.add((collectionHead, ohdsi['adeEffect'], Literal(elt[ADR_HOI_UI])))
    #     adeEffectCollectionCache[elt[PMID]] = [(elt[ADR_HOI_UI],collectionHead)]
    # else:
    #     effectTplL = adeEffectCollectionCache[elt[PMID]]
    #     prevEffectsL = [x[0] for x in effectTplL]
    #     if elt[ADR_HOI_UI] not in prevEffectsL:
    #         collectionHead = effectTplL[0][1] # pull the UUID already create for this collection head to add a new effect
    #         graph.add((collectionHead, ohdsi['adeEffect'], Literal(elt[ADR_HOI_UI])))
    #         adeEffectCollectionCache[elt[PMID]].append((elt[ADR_HOI_UI],collectionHead))

# display the graph
f = codecs.open(OUTPUT_FILE,"w","utf8")
#graph.serialize(destination=f,format="xml",encoding="utf8")
s = graph.serialize(format="xml",encoding="utf8")

#f.write(graph.serialize(format="xml",encoding="utf8"))
f.write(unicode(s,errors='replace'))
#print graph.serialize(format="xml")
f.close

graph.close()
